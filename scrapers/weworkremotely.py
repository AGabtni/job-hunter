import requests
from bs4 import BeautifulSoup
import logging
import re

logger = logging.getLogger(__name__)

# WWR has RSS feeds per category
WWR_FEEDS = [
    "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-front-end-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def scrape_weworkremotely(titles: list[str], exclude_keywords: list[str]) -> list[dict]:
    """Scrape WeWorkRemotely using their RSS feeds."""
    jobs = []
    seen_urls = set()
    
    for feed_url in WWR_FEEDS:
        try:
            logger.info(f"Scraping WWR feed: {feed_url}")
            resp = requests.get(feed_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.content, "html.parser")
            items = soup.find_all("item")
            
            for item in items:
                title_el = item.find("title")
                link_el = item.find("link")
                desc_el = item.find("description")
                pubdate_el = item.find("pubdate")
                
                if not title_el or not link_el:
                    continue
                
                # WWR titles are usually "Company: Job Title"
                raw_title = title_el.get_text(strip=True)
                url = link_el.get_text(strip=True) if link_el.string else (link_el.next_sibling or "").strip()
                
                # Sometimes link is in next sibling text node
                if not url or not url.startswith("http"):
                    url = ""
                    for sibling in link_el.next_siblings:
                        text = str(sibling).strip()
                        if text.startswith("http"):
                            url = text
                            break
                
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                
                # Parse company and title
                if ":" in raw_title:
                    company, title = raw_title.split(":", 1)
                    company = company.strip()
                    title = title.strip()
                else:
                    company = ""
                    title = raw_title
                
                description = ""
                if desc_el:
                    desc_soup = BeautifulSoup(desc_el.get_text(), "html.parser")
                    description = desc_soup.get_text(separator=" ", strip=True)[:2000]
                
                date = pubdate_el.get_text(strip=True) if pubdate_el else ""
                
                combined = f"{title.lower()} {description.lower()}"
                
                # Exclude unwanted
                if any(kw.lower() in combined for kw in exclude_keywords):
                    continue
                
                jobs.append({
                    "title": title,
                    "company": company,
                    "location": "Remote",
                    "url": url,
                    "description": description,
                    "tags": [],
                    "salary_min": None,
                    "salary_max": None,
                    "date_posted": date,
                    "source": "WeWorkRemotely",
                })
                
        except Exception as e:
            logger.error(f"WWR feed scraping failed ({feed_url}): {e}")
    
    logger.info(f"WeWorkRemotely: found {len(jobs)} matching jobs")
    return jobs
