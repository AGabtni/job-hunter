import requests
import logging
import re

logger = logging.getLogger(__name__)

# Jobicy - free remote job API, European focus
JOBICY_API = "https://jobicy.com/api/v2/remote-jobs"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def scrape_jobicy(titles: list[str], exclude_keywords: list[str], blocked_countries: list[str] = None) -> list[dict]:
    """Scrape Jobicy API for remote dev jobs."""
    jobs = []
    seen_urls = set()
    
    titles_lower = [t.lower() for t in titles]
    exclude_lower = [e.lower() for e in exclude_keywords]
    
    # Use tag parameter for keyword search
    tags_to_search = ["developer", "engineer", "fullstack", "frontend", "backend"]
    
    for tag in tags_to_search:
        try:
            resp = requests.get(
                JOBICY_API,
                params={"count": 50, "tag": tag},
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
                
                title = item.get("jobTitle", "")
                title_lower = title.lower()
                
                if any(ex in title_lower for ex in exclude_lower):
                    continue
                
                if not any(t in title_lower for t in titles_lower):
                    if not any(kw in title_lower for kw in ["developer", "engineer", "dev", "frontend", "backend", "fullstack", "full-stack", "full stack"]):
                        continue
                
                description = item.get("jobDescription", "")
                description = re.sub(r'<[^>]+>', ' ', description)
                description = re.sub(r'\s+', ' ', description).strip()
                
                company = item.get("companyName", "")
                location = item.get("jobGeo", "Remote")
                
                # Skip only explicitly restricted geos
                location_lower = location.lower()
                blocked_geos = blocked_countries or []
                if any(b == location_lower.strip() for b in blocked_geos):
                    continue
                salary_min = item.get("annualSalaryMin", "")
                salary_max = item.get("annualSalaryMax", "")
                salary_currency = item.get("salaryCurrency", "")
                salary = ""
                if salary_min and salary_max:
                    salary = f"{salary_currency} {salary_min}-{salary_max}"
                
                date = item.get("pubDate", "")
                
                jobs.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "description": description,
                    "tags": [tag],
                    "salary": salary,
                    "date": date,
                    "url": url,
                    "source": "Jobicy",
                })
            
        except Exception as e:
            logger.error(f"Jobicy [{tag}] error: {e}")
            continue
    
    logger.info(f"Jobicy: {len(jobs)} jobs found")
    return jobs