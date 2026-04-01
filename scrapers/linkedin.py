import requests
from bs4 import BeautifulSoup
import time
import logging
import urllib.parse
import re
import os

logger = logging.getLogger(__name__)

HEADERS_GUEST = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
}

GUEST_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

# ============================================================
# SESSION MANAGEMENT
# ============================================================

def _create_session() -> requests.Session:
    """Create a requests session for guest scraping."""
    session = requests.Session()
    session.headers.update(HEADERS_GUEST)
    return session


# ============================================================
# REMOTE DETECTION (description-based)
# ============================================================

NOT_REMOTE_PATTERNS = re.compile(
    r"|".join([
        r"\bhybrid\b",
        r"\bon[- ]?site\b",
        r"\bin[- ]?office\b",
        r"come into the office",
        r"present in the office",
        r"office.{0,10}(required|mandatory|days? (a|per) week)",
        r"\d+\s*days?.{0,5}(in|at) (the )?office",
        r"fully remote.{0,10}not.{0,10}(option|available|possible)",
        r"remote work is not",
        r"this is not a remote",
        r"not a remote position",
        r"no remote",
        r"must be.{0,15}(on-site|onsite|in office|in the office)",
        r"required to (be|work) (on-site|onsite|in office|in the office)",
        r"work from (the |our )office",
    ]),
    re.IGNORECASE,
)


def is_remote_job(description: str, workplace_type: str = "") -> bool:
    """Check if job is remote. Uses workplace metadata if available, else description."""
    # If we have metadata (from authenticated scraping), trust it
    if workplace_type:
        return workplace_type.lower() == "remote"

    if not description:
        return True  # No data = let it through

    # Check description for non-remote signals
    if NOT_REMOTE_PATTERNS.search(description):
        return False

    return True


def _is_location_allowed(location: str, blocked_countries: list[str] = None) -> bool:
    loc = location.lower().strip()
    if blocked_countries and any(b in loc for b in blocked_countries):
        return False
    return True


# ============================================================
# GUEST SCRAPING (no auth)
# ============================================================

def _search_guest(session: requests.Session, query: str, start: int, max_age_days: int) -> list[dict]:
    """Search LinkedIn jobs via guest API. Returns raw card data."""
    params = {
        "keywords": query,
        "location": "Worldwide",
        "f_WT": "2",
        "f_TPR": f"r{max_age_days * 86400}",
        "start": str(start),
    }
    url = f"{GUEST_SEARCH_URL}?{urllib.parse.urlencode(params)}"
    resp = session.get(url, timeout=15)

    if resp.status_code == 429:
        return None  # Rate limited
    if resp.status_code != 200:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    cards = soup.find_all("div", class_="base-card")
    results = []

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

            results.append({
                "title": title,
                "company": company,
                "location": location,
                "url": job_url,
                "date": date,
                "workplace_type": "",  # Not available in guest mode
            })
        except Exception:
            continue

    return results


def _fetch_description_guest(session: requests.Session, job_url: str) -> str:
    """Fetch job description from guest-accessible job page."""
    try:
        resp = session.get(job_url, timeout=15)
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


# ============================================================
# AUTHENTICATED SCRAPING
# ============================================================

# ============================================================
# MAIN SCRAPER
# ============================================================

def scrape_linkedin(titles: list[str], locations: list[str], exclude_keywords: list[str],
                    blocked_countries: list[str] = None, max_age_days: int = 7,
                    ) -> list[dict]:
    """Scrape LinkedIn jobs. Uses authenticated session if li_at cookie provided, else guest."""
    session = _create_session()

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
        "java developer",
        "typescript developer",
    ]

    # Pass auth flag so search uses correct URL

    for query in search_queries:
        if rate_limited:
            break

        for start in [0, 25, 50, 75, 100]:  # 3 pages per query
            try:
                if start == 0:
                    logger.info(f"LinkedIn search: '{query}'")

                results = _search_guest(session, query, start, max_age_days)

                if results is None:
                    logger.warning("LinkedIn rate limited. Stopping search.")
                    rate_limited = True
                    break

                for card in results:
                    title = card["title"]
                    company = card.get("company", "")
                    location = card.get("location", "Remote")
                    job_url = card.get("url", "")
                    date = card.get("date", "")
                    workplace_type = card.get("workplace_type", "")

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
                        "_workplace_type": workplace_type,  # Internal, used for filtering
                    })

                time.sleep(3)

            except Exception as e:
                logger.error(f"LinkedIn scraping failed for '{query}': {e}")

    if skipped_location:
        logger.info(f"LinkedIn: skipped {skipped_location} jobs (blocked location/non-remote)")

    # Fetch descriptions and filter non-remote
    if jobs:
        logger.info(f"Fetching descriptions for {len(jobs)} LinkedIn jobs...")
        filtered_jobs = []

        for i, job in enumerate(jobs):
            if job["url"]:
                desc = _fetch_description_guest(session, job["url"])
                job["description"] = desc
                if not is_remote_job(desc):
                    logger.info(f"  Skipping (not remote): {job['title']} @ {job['company']}")
                else:
                    filtered_jobs.append(job)
            else:
                filtered_jobs.append(job)

            if i < len(jobs) - 1:
                time.sleep(2)

        skipped_nr = len(jobs) - len(filtered_jobs)
        if skipped_nr:
            logger.info(f"LinkedIn: removed {skipped_nr} non-remote jobs")
        jobs = filtered_jobs

    # Clean internal fields
    for job in jobs:
        job.pop("_workplace_type", None)

    with_desc = sum(1 for j in jobs if j["description"])
    logger.info(f"LinkedIn: found {len(jobs)} jobs ({with_desc} with descriptions)")
    return jobs