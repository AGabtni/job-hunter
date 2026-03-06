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




def fetch_job_description(job_url: str) -> tuple[str, str]:
    """Fetch job description and workplace type. Returns (description, workplace_type)."""
    try:
        resp = requests.get(job_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return "", ""
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Extract description
        desc_div = (
            soup.find("div", class_="show-more-less-html__markup")
            or soup.find("div", class_="description__text")
            or soup.find("section", class_="show-more-less-html")
        )
        description = desc_div.get_text(separator=" ", strip=True)[:3000] if desc_div else ""
        
        # Extract workplace type from detail page
        # LinkedIn shows it in criteria list items or as a specific span
        workplace_type = ""
        page_text = soup.get_text(separator=" ", strip=True).lower()
        
        # Check for workplace type indicators in the page
        # LinkedIn detail pages show "Remote", "On-site", "Hybrid" in job criteria
        criteria_items = soup.find_all("span", class_="description__job-criteria-text")
        for item in criteria_items:
            text = item.get_text(strip=True).lower()
            if text in ["remote", "hybrid", "on-site"]:
                workplace_type = text
                break
        
        # Also check for #LI tags in description
        if not workplace_type and description:
            desc_lower = description.lower()
            if "#li-remote" in desc_lower:
                workplace_type = "remote"
            elif "#li-hybrid" in desc_lower:
                workplace_type = "hybrid"
            elif "#li-onsite" in desc_lower:
                workplace_type = "on-site"
        
        return description, workplace_type
    except Exception as e:
        logger.debug(f"Failed to fetch description from {job_url}: {e}")
        return "", ""


def _is_location_allowed(location: str, blocked_countries: list[str] = None) -> bool:
    loc = location.lower().strip()
    if blocked_countries and any(b in loc for b in blocked_countries):
        return False
    return True


def scrape_linkedin(titles: list[str], locations: list[str], exclude_keywords: list[str], blocked_countries: list[str] = None, max_age_days: int = 7) -> list[dict]:
    jobs = []
    seen_ids = set()
    rate_limited = False
    skipped_location = 0

    search_queries = [
        "full stack developer",
        "fullstack developer",
        "frontend developer",
        "backend developer",
        "web developer",
        "software developer",
        "software engineer",
        "react developer",
        "node.js developer",
        "python developer",
        "java developer",
        "typescript developer",
    ]

    for query in search_queries:
        if rate_limited:
            break

        for start in [0, 25]:
            try:
                if start == 0:
                    logger.info(f"LinkedIn search: '{query}'")

                params = {
                    "keywords": query,
                    "location": "Worldwide",
                    "f_WT": "2",
                    "f_TPR": f"r{max_age_days * 86400}",
                    "start": str(start),
                }

                url = f"{LINKEDIN_BASE}?{urllib.parse.urlencode(params)}"
                resp = requests.get(url, headers=HEADERS, timeout=15)

                if resp.status_code == 429:
                    logger.warning("LinkedIn rate limited. Stopping search.")
                    rate_limited = True
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

                        if not _is_location_allowed(location, blocked_countries):
                            skipped_location += 1
                            continue

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

    if skipped_location:
        logger.info(f"LinkedIn: skipped {skipped_location} jobs (blocked location)")

    if jobs:
        logger.info(f"Fetching descriptions for {len(jobs)} LinkedIn jobs...")
        filtered_jobs = []
        for i, job in enumerate(jobs):
            if job["url"]:
                desc, workplace = fetch_job_description(job["url"])
                job["description"] = desc
                # Filter out non-remote jobs based on detail page metadata
                if workplace and workplace != "remote":
                    logger.debug(f"Skipping (workplace: {workplace}): {job['title']}")
                else:
                    filtered_jobs.append(job)
            else:
                filtered_jobs.append(job)
            if i < len(jobs) - 1:
                time.sleep(2)
        skipped_wp = len(jobs) - len(filtered_jobs)
        if skipped_wp:
            logger.info(f"LinkedIn: skipped {skipped_wp} jobs (non-remote workplace)")
        jobs = filtered_jobs

    with_desc = sum(1 for j in jobs if j["description"])
    logger.info(f"LinkedIn: found {len(jobs)} jobs ({with_desc} with descriptions)")
    return jobs