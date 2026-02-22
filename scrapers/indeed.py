import requests
from bs4 import BeautifulSoup
import logging
import urllib.parse
import time

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Indeed RSS feed base URL
INDEED_RSS_BASE = "https://www.indeed.com/rss"


def scrape_indeed(titles: list[str], locations: list[str], exclude_keywords: list[str]) -> list[dict]:
    """Scrape Indeed using RSS feeds (more reliable than HTML scraping)."""
    jobs = []
    seen_urls = set()
    
    search_queries = [
        ("full stack developer", "remote"),
        ("fullstack developer", "remote"),
        ("web developer", "remote"),
        ("software developer remote", ""),
    ]
    
    for query, location in search_queries:
        try:
            logger.info(f"Indeed RSS search: '{query}' in '{location}'")
            
            params = {
                "q": query,
                "l": location,
                "sort": "date",
                "fromage": "7",  # Past 7 days
            }
            
            url = f"{INDEED_RSS_BASE}?{urllib.parse.urlencode(params)}"
            resp = requests.get(url, headers=HEADERS, timeout=15)
            
            if resp.status_code != 200:
                logger.warning(f"Indeed returned {resp.status_code}")
                continue
            
            soup = BeautifulSoup(resp.content, "html.parser")
            items = soup.find_all("item")
            
            for item in items:
                title_el = item.find("title")
                link_el = item.find("link")
                desc_el = item.find("description")
                pubdate_el = item.find("pubdate")
                source_el = item.find("source")
                
                if not title_el:
                    continue
                
                title = title_el.get_text(strip=True)
                
                # Indeed RSS link handling
                job_url = ""
                if link_el:
                    job_url = link_el.get_text(strip=True)
                    if not job_url:
                        job_url = link_el.next_sibling
                        if job_url:
                            job_url = str(job_url).strip()
                
                if not job_url or job_url in seen_urls:
                    continue
                seen_urls.add(job_url)
                
                company = source_el.get_text(strip=True) if source_el else ""
                date = pubdate_el.get_text(strip=True) if pubdate_el else ""
                
                description = ""
                if desc_el:
                    desc_text = desc_el.get_text()
                    desc_soup = BeautifulSoup(desc_text, "html.parser")
                    description = desc_soup.get_text(separator=" ", strip=True)[:2000]
                
                combined = f"{title.lower()} {description.lower()}"
                
                if any(kw.lower() in combined for kw in exclude_keywords):
                    continue
                
                jobs.append({
                    "title": title,
                    "company": company,
                    "location": "Remote",
                    "url": job_url,
                    "description": description,
                    "tags": [],
                    "salary_min": None,
                    "salary_max": None,
                    "date_posted": date,
                    "source": "Indeed",
                })
                
            time.sleep(2)
            
        except Exception as e:
            logger.error(f"Indeed scraping failed for '{query}': {e}")
    
    logger.info(f"Indeed: found {len(jobs)} matching jobs")
    return jobs
