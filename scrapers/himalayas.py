import requests
import logging
import re

logger = logging.getLogger(__name__)

HIMALAYAS_API = "https://himalayas.app/jobs/api"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

# Dev-related categories on Himalayas
DEV_CATEGORIES = [
    "software engineering", "software development", "web development",
    "frontend", "backend", "full stack", "fullstack", "engineering",
]


def scrape_himalayas(titles: list[str], exclude_keywords: list[str], blocked_countries: list[str] = None) -> list[dict]:
    """Scrape Himalayas API for remote dev jobs. Free, no auth needed. Max 20 per request."""
    jobs = []
    seen_urls = set()

    titles_lower = [t.lower() for t in titles]
    exclude_lower = [e.lower() for e in exclude_keywords]
    blocked = [b.lower() for b in (blocked_countries or [])]

    # Paginate through results (API returns all jobs, we filter for dev roles)
    for offset in range(0, 200, 20):
        try:
            resp = requests.get(
                HIMALAYAS_API,
                params={"limit": 20, "offset": offset},
                headers=HEADERS,
                timeout=15,
            )

            if resp.status_code == 429:
                logger.warning("Himalayas: rate limited, stopping")
                break

            if resp.status_code != 200:
                logger.warning(f"Himalayas: returned {resp.status_code}")
                break

            data = resp.json()

            # API returns a list directly or {"jobs": [...]}
            if isinstance(data, list):
                job_list = data
            elif isinstance(data, dict):
                job_list = data.get("jobs", data.get("results", []))
            else:
                break

            if not job_list:
                break

            for item in job_list:
                # Use correct field names from API docs
                url = item.get("applicationLink", "") or item.get("url", "")

                if not url:
                    continue

                if url in seen_urls:
                    continue
                seen_urls.add(url)

                title = item.get("title", "")
                title_lower = title.lower()

                # Exclude check
                if any(ex in title_lower for ex in exclude_lower):
                    continue

                # Check if this is a dev role by title or category
                categories = item.get("category", []) or item.get("parentCategories", [])
                if isinstance(categories, str):
                    categories = [categories]
                cat_str = " ".join(c.lower() for c in categories)

                is_dev_title = any(t in title_lower for t in titles_lower) or any(
                    kw in title_lower for kw in [
                        "developer", "engineer", "dev", "frontend", "backend",
                        "fullstack", "full-stack", "full stack", "programmer"
                    ]
                )
                is_dev_category = any(dc in cat_str for dc in DEV_CATEGORIES)

                if not (is_dev_title or is_dev_category):
                    continue

                company = item.get("companyName", "")

                # Location from restrictions
                loc_restrictions = item.get("locationRestrictions", [])
                if loc_restrictions and isinstance(loc_restrictions, list):
                    location = f"Remote ({', '.join(loc_restrictions)})"
                else:
                    location = "Remote (Worldwide)"

                # Block low-salary locations
                if blocked:
                    loc_lower = location.lower()
                    if any(b in loc_lower for b in blocked):
                        continue

                description = item.get("description", "")
                # Strip HTML tags
                description = re.sub(r'<[^>]+>', ' ', description)
                description = re.sub(r'\s+', ' ', description).strip()

                salary_min = item.get("minSalary")
                salary_max = item.get("maxSalary")
                currency = item.get("currency", "")
                salary = ""
                if salary_min and salary_max:
                    salary = f"{currency} {salary_min}-{salary_max}"

                date = item.get("pubDate", "")
                tags = categories

                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "description": description[:3000],
                    "tags": tags,
                    "salary": salary,
                    "date": date,
                    "url": url,
                    "source": "Himalayas",
                })

        except Exception as e:
            logger.error(f"Himalayas [offset={offset}] error: {e}")
            break

    logger.info(f"Himalayas: {len(jobs)} jobs found")
    return jobs