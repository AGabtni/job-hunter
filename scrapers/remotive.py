import requests
import logging

logger = logging.getLogger(__name__)

# Remotive - free remote job API
REMOTIVE_API = "https://remotive.com/api/remote-jobs"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

# Remotive category slugs for dev jobs
CATEGORIES = ["software-dev", "frontend-dev", "backend-dev", "web-dev"]


def scrape_remotive(titles: list[str], exclude_keywords: list[str]) -> list[dict]:
    """Scrape Remotive API for remote dev jobs."""
    jobs = []
    seen_urls = set()
    
    titles_lower = [t.lower() for t in titles]
    exclude_lower = [e.lower() for e in exclude_keywords]
    
    for category in CATEGORIES:
        try:
            resp = requests.get(
                REMOTIVE_API,
                params={"category": category, "limit": 50},
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            
            for item in data.get("jobs", []):
                url = item.get("url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                
                title = item.get("title", "")
                title_lower = title.lower()
                
                # Exclude check
                if any(ex in title_lower for ex in exclude_lower):
                    continue
                
                # Title match (loose)
                if not any(t in title_lower for t in titles_lower):
                    # Also check against common dev keywords
                    if not any(kw in title_lower for kw in ["developer", "engineer", "dev", "frontend", "backend", "fullstack", "full-stack", "full stack"]):
                        continue
                
                description = item.get("description", "")
                # Strip HTML tags from description
                import re
                description = re.sub(r'<[^>]+>', ' ', description)
                description = re.sub(r'\s+', ' ', description).strip()
                
                company = item.get("company_name", "")
                location = item.get("candidate_required_location", "Worldwide")
                salary = item.get("salary", "")
                date = item.get("publication_date", "")
                tags = item.get("tags", [])
                
                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "description": description,
                    "tags": tags if isinstance(tags, list) else [],
                    "salary": salary,
                    "date": date,
                    "url": url,
                    "source": "Remotive",
                })
            
            logger.info(f"Remotive [{category}]: {len(data.get('jobs', []))} raw, {len(jobs)} total kept")
            
        except Exception as e:
            logger.error(f"Remotive [{category}] error: {e}")
            continue
    
    logger.info(f"Remotive: {len(jobs)} jobs found")
    return jobs
