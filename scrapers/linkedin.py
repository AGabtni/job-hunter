import requests
from bs4 import BeautifulSoup
import time
import logging
import urllib.parse

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
}

LINKEDIN_BASE = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"


def fetch_job_description(job_url: str) -> str:
    """Fetch full job description from LinkedIn job page (no auth needed)."""
    try:
        resp = requests.get(job_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return ""

        soup = BeautifulSoup(resp.text, "html.parser")

        desc_div = (
            soup.find("div", class_="show-more-less-html__markup")
            or soup.find("div", class_="description__text")
            or soup.find("section", class_="show-more-less-html")
        )

        if desc_div:
            return desc_div.get_text(separator=" ", strip=True)[:3000]

        return ""
    except Exception as e:
        logger.debug(f"Failed to fetch description from {job_url}: {e}")
        return ""


def scrape_linkedin(titles: list[str], locations: list[str], exclude_keywords: list[str]) -> list[dict]:
    """Scrape LinkedIn public job listings (no auth required)."""
    jobs = []
    seen_ids = set()

    search_queries = [
        "full stack developer remote",
        "fullstack developer remote",
        "développeur full stack",
        "web developer remote",
        "software developer remote",
    ]

    for query in search_queries:
        try:
            logger.info(f"LinkedIn search: '{query}'")

            params = {
                "keywords": query,
                "location": "Worldwide",
                "f_WT": "2",
                "f_TPR": "r604800",
                "start": "0",
            }

            url = f"{LINKEDIN_BASE}?{urllib.parse.urlencode(params)}"
            resp = requests.get(url, headers=HEADERS, timeout=15)

            if resp.status_code == 429:
                logger.warning("LinkedIn rate limited. Stopping search.")
                break

            if resp.status_code != 200:
                logger.warning(f"LinkedIn returned {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.find_all("div", class_="base-card")

            for card in cards:
                try:
                    title_el = card.find("h3", class_="base-search-card__title")
                    company_el = card.find("h4", class_="base-search-card__subtitle")
                    location_el = card.find("span", class_="job-search-card__location")
                    link_el = card.find("a", class_="base-card__full-link")
                    time_el = card.find("time")

                    if not title_el:
                        continue

                    title = title_el.get_text(strip=True)
                    company = company_el.get_text(strip=True) if company_el else ""
                    location = location_el.get_text(strip=True) if location_el else "Remote"
                    job_url = link_el["href"].split("?")[0] if link_el and link_el.get("href") else ""
                    date = time_el.get("datetime", "") if time_el else ""

                    job_id = job_url or f"{company}-{title}"
                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)

                    combined = f"{title.lower()} {company.lower()} {location.lower()}"

                    if any(kw.lower() in combined for kw in exclude_keywords):
                        continue

                    jobs.append({
                        "title": title,
                        "company": company,
                        "location": location,
                        "url": job_url,
                        "description": "",
                        "tags": [],
                        "salary_min": None,
                        "salary_max": None,
                        "date_posted": date,
                        "source": "LinkedIn",
                    })
                except Exception as e:
                    logger.debug(f"Error parsing LinkedIn card: {e}")
                    continue

            time.sleep(3)

        except Exception as e:
            logger.error(f"LinkedIn scraping failed for '{query}': {e}")

    # Fetch full descriptions for all LinkedIn jobs
    if jobs:
        logger.info(f"Fetching descriptions for {len(jobs)} LinkedIn jobs...")
        for i, job in enumerate(jobs):
            if job["url"]:
                desc = fetch_job_description(job["url"])
                job["description"] = desc
                if desc:
                    logger.debug(f"  Got description for: {job['title']}")
                else:
                    logger.debug(f"  No description found for: {job['title']}")

            if i < len(jobs) - 1:
                time.sleep(2)

    with_desc = sum(1 for j in jobs if j["description"])
    logger.info(f"LinkedIn: found {len(jobs)} jobs ({with_desc} with descriptions)")
    return jobs