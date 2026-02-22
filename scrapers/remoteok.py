import requests
import time
import logging

logger = logging.getLogger(__name__)

REMOTEOK_API = "https://remoteok.com/api"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def scrape_remoteok(titles: list[str], exclude_keywords: list[str]) -> list[dict]:
    """Scrape RemoteOK using their public JSON API."""
    jobs = []
    
    try:
        logger.info("Scraping RemoteOK...")
        resp = requests.get(REMOTEOK_API, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        # First item is metadata, skip it
        listings = data[1:] if len(data) > 1 else []
        
        for item in listings:
            title = item.get("position", "").strip()
            company = item.get("company", "").strip()
            description = item.get("description", "")
            tags = item.get("tags", [])
            url = item.get("url", "")
            date = item.get("date", "")
            salary_min = item.get("salary_min")
            salary_max = item.get("salary_max")
            location = item.get("location", "Worldwide")
            
            if not title:
                continue
            
            # Check if title matches any of our search titles
            title_lower = title.lower()
            tags_lower = [t.lower() for t in tags] if tags else []
            combined = f"{title_lower} {' '.join(tags_lower)} {description.lower()}"
            
            title_match = any(t.lower() in title_lower for t in titles)
            tag_match = any(
                keyword in combined
                for keyword in ["fullstack", "full stack", "full-stack", "frontend", "backend", "web dev", "software engineer", "software developer"]
            )
            
            if not (title_match or tag_match):
                continue
            
            # Exclude unwanted keywords
            if any(kw.lower() in combined for kw in exclude_keywords):
                continue
            
            full_url = f"https://remoteok.com{url}" if url and not url.startswith("http") else url
            
            jobs.append({
                "title": title,
                "company": company,
                "location": location or "Remote",
                "url": full_url,
                "description": description[:2000],
                "tags": tags or [],
                "salary_min": salary_min,
                "salary_max": salary_max,
                "date_posted": date,
                "source": "RemoteOK",
            })
        
        logger.info(f"RemoteOK: found {len(jobs)} matching jobs")
        
    except Exception as e:
        logger.error(f"RemoteOK scraping failed: {e}")
    
    return jobs
