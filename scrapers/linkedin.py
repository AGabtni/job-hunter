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

HEADERS_AUTH = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
    "csrf-token": "ajax:0",
}

GUEST_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
AUTH_SEARCH_URL = "https://www.linkedin.com/voyager/api/voyagerJobsDashJobCards"

# ============================================================
# SESSION MANAGEMENT
# ============================================================

def _create_session(li_at: str = "") -> tuple[requests.Session, bool]:
    """Create a requests session. If li_at cookie provided, try authenticated session.
    Returns (session, is_authenticated)."""
    session = requests.Session()

    # Try li_at from param, then env var
    cookie = li_at or os.environ.get("LINKEDIN_LI_AT", "")
    if not cookie:
        session.headers.update(HEADERS_GUEST)
        return session, False

    # Set auth cookies
    session.cookies.set("li_at", cookie, domain=".linkedin.com")
    session.headers.update(HEADERS_AUTH)

    # Verify session works
    try:
        resp = session.get("https://www.linkedin.com/voyager/api/me", timeout=10)
        if resp.status_code == 200:
            logger.info("LinkedIn: authenticated session active")
            return session, True
        else:
            logger.warning(f"LinkedIn: auth failed (status {resp.status_code}), falling back to guest")
            session.cookies.clear()
            session.headers.update(HEADERS_GUEST)
            return session, False
    except Exception as e:
        logger.warning(f"LinkedIn: auth check failed ({e}), falling back to guest")
        session.cookies.clear()
        session.headers.update(HEADERS_GUEST)
        return session, False


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

def _search_auth(session: requests.Session, query: str, start: int, max_age_days: int) -> list[dict]:
    """Search LinkedIn jobs via authenticated Voyager API. Returns structured results."""
    params = {
        "decorationId": "com.linkedin.voyager.dash.deco.jobs.search.JobSearchCardsCollection-227",
        "count": 25,
        "q": "jserpFilters",
        "queryContext": f"List(primaryHitType->JOBS,spellCorrectionEnabled->true)",
        "keywords": query,
        "locationFallback": "Worldwide",
        "f_WT": "2",  # Remote
        "f_TPR": f"r{max_age_days * 86400}",
        "start": start,
    }

    try:
        resp = session.get(AUTH_SEARCH_URL, params=params, timeout=15)
        if resp.status_code == 429:
            return None
        if resp.status_code != 200:
            logger.debug(f"Auth search returned {resp.status_code}")
            return []

        data = resp.json()
        results = []

        for element in data.get("included", []):
            # Job posting entities
            if element.get("$type") == "com.linkedin.voyager.dash.jobs.JobPosting":
                job_id = element.get("entityUrn", "").split(":")[-1]
                results.append({
                    "title": element.get("title", ""),
                    "company": "",  # Filled from related entity
                    "location": element.get("formattedLocation", "Remote"),
                    "url": f"https://www.linkedin.com/jobs/view/{job_id}/",
                    "date": "",
                    "workplace_type": element.get("workplaceType", ""),
                    "job_id": job_id,
                })

            # Company entities — match back to jobs
            if element.get("$type") == "com.linkedin.voyager.organization.Company":
                company_name = element.get("name", "")
                # Will be matched later if needed

        # Try to extract from elements array if above didn't work
        if not results:
            for element in data.get("included", []):
                title = element.get("jobTitle", "") or element.get("title", "")
                if title and element.get("entityUrn", "").startswith("urn:li:fs_normalized"):
                    job_id = element.get("entityUrn", "").split(":")[-1]
                    location = element.get("formattedLocation", "") or element.get("locationName", "Remote")
                    workplace = element.get("workplaceType", "")
                    company = element.get("companyName", "")
                    results.append({
                        "title": title,
                        "company": company,
                        "location": location,
                        "url": f"https://www.linkedin.com/jobs/view/{job_id}/",
                        "date": "",
                        "workplace_type": workplace,
                        "job_id": job_id,
                    })

        return results
    except Exception as e:
        logger.debug(f"Auth search failed: {e}")
        return []


def _fetch_description_auth(session: requests.Session, job_url: str) -> tuple[str, str]:
    """Fetch job description via authenticated session. Returns (description, workplace_type)."""
    try:
        # Extract job ID from URL
        job_id = job_url.rstrip("/").split("/")[-1].split("?")[0]

        # Try Voyager API first
        api_url = f"https://www.linkedin.com/voyager/api/jobs/jobPostings/{job_id}"
        resp = session.get(api_url, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            desc = data.get("description", {}).get("text", "")
            workplace = data.get("workplaceType", "")

            # Normalize workplace type
            workplace_map = {
                "REMOTE": "remote",
                "HYBRID": "hybrid",
                "ON_SITE": "on-site",
                "1": "on-site",
                "2": "remote",
                "3": "hybrid",
            }
            workplace = workplace_map.get(str(workplace).upper(), workplace.lower() if workplace else "")

            return desc[:3000], workplace

        # Fallback: fetch the HTML page with auth cookies
        resp = session.get(job_url, timeout=15)
        if resp.status_code != 200:
            return "", ""

        soup = BeautifulSoup(resp.text, "html.parser")
        desc_div = (
            soup.find("div", class_="show-more-less-html__markup")
            or soup.find("div", class_="description__text")
            or soup.find("div", class_="jobs-description__content")
        )
        description = desc_div.get_text(separator=" ", strip=True)[:3000] if desc_div else ""

        # Try to find workplace badge in authenticated HTML
        workplace = ""
        workplace_el = (
            soup.find("span", class_="ui-label--accent-3")  # Remote badge
            or soup.find("span", class_="jobs-unified-top-card__workplace-type")
        )
        if workplace_el:
            workplace = workplace_el.get_text(strip=True).lower()

        return description, workplace
    except Exception as e:
        logger.debug(f"Auth description fetch failed for {job_url}: {e}")
        return "", ""


# ============================================================
# MAIN SCRAPER
# ============================================================

def scrape_linkedin(titles: list[str], locations: list[str], exclude_keywords: list[str],
                    blocked_countries: list[str] = None, max_age_days: int = 7,
                    li_at: str = "") -> list[dict]:
    """Scrape LinkedIn jobs. Uses authenticated session if li_at cookie provided, else guest."""
    session, authenticated = _create_session(li_at)
    mode = "authenticated" if authenticated else "guest"
    logger.info(f"LinkedIn: scraping in {mode} mode")

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

    search_fn = _search_auth if authenticated else _search_guest

    for query in search_queries:
        if rate_limited:
            break

        for start in [0, 25]:
            try:
                if start == 0:
                    logger.info(f"LinkedIn search: '{query}'")

                results = search_fn(session, query, start, max_age_days)

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

                    # In auth mode, filter by workplace metadata immediately
                    if authenticated and workplace_type:
                        wt = workplace_type.lower()
                        if wt in ("hybrid", "on-site", "on_site"):
                            skipped_location += 1
                            continue

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
                if authenticated:
                    desc, workplace = _fetch_description_auth(session, job["url"])
                    job["description"] = desc
                    if not is_remote_job(desc, workplace):
                        logger.info(f"  Skipping (not remote): {job['title']} @ {job['company']}")
                    else:
                        filtered_jobs.append(job)
                else:
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