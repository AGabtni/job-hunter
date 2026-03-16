import requests
import logging
import re

logger = logging.getLogger(__name__)

WORKINGNOMADS_API = "https://www.workingnomads.com/api/exposed_jobs/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def scrape_workingnomads(titles: list[str], exclude_keywords: list[str], blocked_countries: list[str] = None) -> list[dict]:
    """Scrape Working Nomads API for remote dev jobs. Free, no auth needed."""
    jobs = []
    seen_urls = set()

    titles_lower = [t.lower() for t in titles]
    exclude_lower = [e.lower() for e in exclude_keywords]
    blocked = [b.lower() for b in (blocked_countries or [])]

    try:
        resp = requests.get(WORKINGNOMADS_API, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, list):
            data = data.get("jobs", [])

        for item in data:
            url = item.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            title = item.get("title", "")
            title_lower = title.lower()
            category = item.get("category_name", "").lower()

            # Only keep development jobs
            if category not in ["development", "sysadmin", ""]:
                continue

            # Exclude check
            if any(ex in title_lower for ex in exclude_lower):
                continue

            # Title relevance
            if not any(t in title_lower for t in titles_lower):
                if not any(kw in title_lower for kw in [
                    "developer", "engineer", "dev", "frontend", "backend",
                    "fullstack", "full-stack", "full stack", "programmer"
                ]):
                    continue

            company = item.get("company_name", "")
            location = item.get("location", "Remote")

            # Block low-salary locations
            if blocked:
                loc_lower = location.lower()
                if any(b in loc_lower for b in blocked):
                    continue

            description = item.get("description", "")
            description = re.sub(r'<[^>]+>', ' ', description)
            description = re.sub(r'\s+', ' ', description).strip()

            tags_str = item.get("tags", "")
            tags = [t.strip() for t in tags_str.split(",")] if tags_str else []

            date = item.get("pub_date", "")

            jobs.append({
                "title": title,
                "company": company,
                "location": location,
                "description": description[:3000],
                "tags": tags,
                "salary": "",
                "date": date,
                "url": url,
                "source": "WorkingNomads",
            })

    except Exception as e:
        logger.error(f"WorkingNomads error: {e}")

    logger.info(f"WorkingNomads: {len(jobs)} jobs found")
    return jobs
