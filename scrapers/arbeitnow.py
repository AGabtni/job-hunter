import requests
import logging

logger = logging.getLogger(__name__)

# Arbeitnow - free European remote job API, no auth needed
ARBEITNOW_API = "https://www.arbeitnow.com/api/job-board-api"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def scrape_arbeitnow(titles: list[str], exclude_keywords: list[str]) -> list[dict]:
    """Scrape Arbeitnow European job board API."""
    jobs = []
    page = 1
    max_pages = 3  # Don't go crazy

    while page <= max_pages:
        try:
            logger.info(f"Scraping Arbeitnow page {page}...")
            resp = requests.get(f"{ARBEITNOW_API}?page={page}", headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            listings = data.get("data", [])
            if not listings:
                break

            for item in listings:
                title = item.get("title", "").strip()
                company = item.get("company_name", "").strip()
                description = item.get("description", "")
                tags = item.get("tags", [])
                url = item.get("url", "")
                location = item.get("location", "")
                remote = item.get("remote", False)
                date = item.get("created_at", "")

                if not title:
                    continue

                # Only remote jobs
                if not remote and "remote" not in location.lower():
                    continue

                title_lower = title.lower()
                tags_lower = [t.lower() for t in tags] if tags else []
                # Strip HTML from description
                from bs4 import BeautifulSoup
                clean_desc = BeautifulSoup(description, "html.parser").get_text(separator=" ", strip=True)
                combined = f"{title_lower} {' '.join(tags_lower)} {clean_desc.lower()}"

                # Check relevance
                relevant_keywords = [
                    "fullstack", "full stack", "full-stack", "frontend", "front-end",
                    "backend", "back-end", "web dev", "software engineer",
                    "software developer", "développeur", "web developer",
                ]
                title_match = any(t.lower() in title_lower for t in titles)
                keyword_match = any(kw in combined for kw in relevant_keywords)

                if not (title_match or keyword_match):
                    continue

                if any(kw.lower() in combined for kw in exclude_keywords):
                    continue

                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location or ("Remote" if remote else "Unknown"),
                    "url": url,
                    "description": clean_desc[:2000],
                    "tags": tags or [],
                    "salary_min": None,
                    "salary_max": None,
                    "date_posted": date,
                    "source": "Arbeitnow",
                })

            # Check for next page
            if not data.get("links", {}).get("next"):
                break
            page += 1

        except Exception as e:
            logger.error(f"Arbeitnow scraping failed (page {page}): {e}")
            break

    logger.info(f"Arbeitnow: found {len(jobs)} matching remote jobs")
    return jobs
