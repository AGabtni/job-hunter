#!/usr/bin/env python3
"""
Job Finder Module
=================
Scrapes multiple job boards, filters, scores, outputs ranked jobs.json.

Standalone:
    python job_finder.py                      # Full run -> output/jobs.json
    python job_finder.py -o my_jobs.json      # Custom output
    python job_finder.py --no-history         # Ignore seen_jobs

Pipeline:
    from job_finder import find_jobs
    jobs = find_jobs(config)
"""

import re
import os
import json
import yaml
import logging
import argparse
from pathlib import Path

from scrapers.remoteok import scrape_remoteok
from scrapers.linkedin import scrape_linkedin
from scrapers.arbeitnow import scrape_arbeitnow
from scrapers.remotive import scrape_remotive
from scrapers.jobicy import scrape_jobicy

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).parent


# --- Language detection ---
LANGUAGE_PATTERNS = {
    "German": ["arbeiten", "erfahrung", "kenntnisse", "anforderungen", "aufgaben",
               "bewerbung", "unternehmen", "stellenangebot", "verantwortung",
               "entwicklung", "mindestens", "berufserfahrung", "und", "oder", "wir suchen"],
    "Spanish": ["experiencia", "requisitos", "responsabilidades", "conocimientos",
                "empresa", "desarrollo", "habilidades", "trabajar", "buscamos"],
    "Portuguese": ["experiência", "requisitos", "responsabilidades", "conhecimentos",
                   "empresa", "desenvolvimento", "habilidades", "trabalhar"],
    "Dutch": ["ervaring", "vereisten", "verantwoordelijkheden", "kennis",
              "bedrijf", "ontwikkeling", "vaardigheden", "werken"],
    "Italian": ["esperienza", "requisiti", "responsabilità", "conoscenze",
                "azienda", "sviluppo", "competenze", "lavorare"],
}

LOCATION_EXCLUSION_RE = re.compile(
    r'|'.join([
        # Explicitly NOT remote
        r'fully remote.{0,10}not an option',
        r'remote work is not.{0,10}(option|available|possible)',
        r'this.{0,15}(is not|isn.t).{0,15}remote',
        r'not.{0,5}a? ?remote.{0,10}(position|role)',
        r'no remote',
        # On-site / in-office as work arrangement
        r'(work|job) (arrangement|type|mode|style).{0,15}(on[- ]?site|in[- ]?office|in[- ]?person|hybrid)',
        r'this (is|position is|role is).{0,10}(an? )?(on[- ]?site|in[- ]?office|in[- ]?person|hybrid)',
        r'\b(on[- ]?site|in[- ]?person|hybrid) (position|role|job|work)\b',
        # Must be physically present
        r'must.{0,15}(come|be present|report).{0,15}(in |at |to )?(the )?office',
        r'required to (be in|work from|report to) (the |our )?office',
        r'present in the office',
        r'come into the office',
        # Residency / location lock
        r'residency in \w+',
        r'must (be|have) residen(cy|ce) in',
        r'candidates based in',
        # Applications explicitly excluded by distance
        r'applications from.{0,30}(distant|other).{0,20}not.{0,10}considered',
        # Work authorization
        r'\bauthori[sz]ed to work in\b',
        r'\bwork (authori[sz]ation|permit) required\b',
        r'\bwork visa.{0,10}not.{0,10}sponsor',
        r'\bno visa sponsorship\b',
        # Fluent German = locked to DACH market
        r'fluent.{0,5}(in )?german',
        r'\bgerman.{0,5}(c1|c2|native|fluent|required|mandatory)\b',
    ]), re.IGNORECASE)


def _scrape_all(config: dict) -> list[dict]:
    search = config["search"]
    titles, locations, exclude = search["titles"], search["locations"], search["exclude_keywords"]
    blocked = [c.lower().strip() for c in search.get("blocked_countries", []) if c.strip()]
    max_age = search.get("max_age_days", 7)
    all_jobs = []
    all_jobs.extend(scrape_remoteok(titles, exclude, blocked_countries=blocked))
    li_at = config.get("linkedin", {}).get("li_at", "") or os.environ.get("LINKEDIN_LI_AT", "")
    all_jobs.extend(scrape_linkedin(titles, locations, exclude, blocked_countries=blocked, max_age_days=max_age, li_at=li_at))
    all_jobs.extend(scrape_arbeitnow(titles, exclude, blocked_countries=blocked))
    all_jobs.extend(scrape_remotive(titles, exclude, blocked_countries=blocked))
    all_jobs.extend(scrape_jobicy(titles, exclude, blocked_countries=blocked))
    logger.info(f"Total scraped: {len(all_jobs)}")
    return all_jobs


def _deduplicate(jobs, seen):
    unique, urls, signatures = [], set(), set()
    for job in jobs:
        url = job.get("url", "")
        if not url or url in urls or url in seen:
            continue
        # Also dedup by company + title (same job on different boards)
        sig = f"{job.get('company', '').lower().strip()}|{job.get('title', '').lower().strip()}"
        if sig in signatures:
            continue
        urls.add(url)
        signatures.add(sig)
        unique.append(job)
    logger.info(f"After dedup: {len(unique)} new ({len(jobs) - len(unique)} removed)")
    return unique


def _filter_jobs(jobs, config):
    exclude_companies = [c.lower().strip() for c in config.get("search", {}).get("exclude_companies", []) if c.strip()]
    
    # Locations we CAN work from
    allowed_location_words = [
        "anywhere", "worldwide", "global", "remote",
        "canada", "tunisia", "africa", "mena",
    ]
    # Locations we CANNOT work from (checked against location field only)
    blocked_location_words = [c.lower().strip() for c in config.get("search", {}).get("blocked_countries", []) if c.strip()]
    
    filtered = []
    for job in jobs:
        desc_lower = job.get("description", "").lower()
        company_lower = job.get("company", "").lower()
        location_lower = job.get("location", "").lower()
        
        # Company exclusion
        if exclude_companies and any(ec in company_lower for ec in exclude_companies):
            logger.debug(f"Skipping (excluded company): {job.get('company', '?')}")
            continue
        
        # Language check
        skip = False
        for lang, patterns in LANGUAGE_PATTERNS.items():
            if sum(1 for p in patterns if p in desc_lower) >= 5:
                logger.debug(f"Skipping ({lang}): {job.get('title', '?')}")
                skip = True
                break
        if skip:
            continue
        
        # Description-level location check (catches "US only", "EU work permit required", etc.)
        full = f"{desc_lower} {location_lower}"
        if LOCATION_EXCLUSION_RE.search(full):
            logger.debug(f"Skipping (location-restricted): {job.get('title', '?')}")
            continue
        
        # Location field check: if location specifies a blocked country/city AND doesn't say "remote"/"anywhere"
        if location_lower and location_lower not in ["", "remote"]:
            is_allowed = any(a in location_lower for a in allowed_location_words)
            is_blocked = any(b in location_lower for b in blocked_location_words)
            if is_blocked and not is_allowed:
                logger.debug(f"Skipping (blocked location '{job.get('location', '')}'): {job.get('title', '?')}")
                continue
        
        filtered.append(job)
    logger.info(f"After filters: {len(filtered)} ({len(jobs) - len(filtered)} removed)")
    return filtered


def _score_jobs(jobs, config):
    profile = config["profile"]
    scoring = config["scoring"]
    search = config["search"]
    core = [s.lower() for s in profile["core_skills"]]
    secondary = [s.lower() for s in profile.get("secondary_skills", [])]
    titles = [t.lower() for t in search["titles"]]
    remote_kw = ["remote", "anywhere", "worldwide", "work from home", "wfh", "distributed"]

    for job in jobs:
        tl = job["title"].lower()
        dl = job.get("description", "").lower()
        ll = job.get("location", "").lower()
        tags_l = " ".join(t.lower() for t in job.get("tags", []))
        c = f"{tl} {dl} {tags_l}"

        cm = sum(1 for s in core if s in c)
        sm = sum(1 for s in secondary if s in c)
        tech = min(1.0, (cm * 1.5 + sm * 0.5) / (len(core) * 0.4)) if core else 0
        remote = 1.0 if any(kw in c or kw in ll for kw in remote_kw) else 0.2
        
        # Location scoring: can only work from Canada or Tunisia
        good_locs = ["anywhere", "worldwide", "global", "canada", "tunisia", "africa", "mena", "middle east", "north africa"]
        bad_locs = ["us only", "usa only", "united states", "eu only", "europe only", "uk only", "india only", "latam only"]
        if any(g in ll for g in good_locs):
            loc = 1.0
        elif any(b in ll for b in bad_locs):
            loc = 0.05  # Nearly kill it
        else:
            loc = 0.4  # Unknown — might be OK
        title = 0.3
        for st in titles:
            if st in tl:
                title = 1.0
                break
            if len(set(st.split()) & set(tl.split())) >= 2:
                title = max(title, 0.7)

        # Relevance check: must be a dev/engineering IC role, not management or non-dev
        dev_keywords = ["developer", "développeur", "programmer", "architect"]
        # "engineer" only counts if NOT preceded by "customer", "sales", "support", "solutions"
        has_dev_keyword = any(dk in tl for dk in dev_keywords)
        if not has_dev_keyword and "engineer" in tl:
            non_dev_prefixes = ["customer", "sales", "support", "solutions", "field", "site reliability"]
            has_dev_keyword = not any(p in tl for p in non_dev_prefixes)
        # "manager" roles are never dev roles
        if "manager" in tl and "developer" not in tl:
            has_dev_keyword = False

        total = tech * scoring["tech_match"] + remote * scoring["remote_match"] + loc * scoring["location_match"] + title * scoring["title_match"]
        
        if not has_dev_keyword:
            total *= 0.15  # Crush score for non-dev roles
        job["score"] = round(total, 3)
        job["score_breakdown"] = {"tech": round(tech, 2), "remote": round(remote, 2), "location": round(loc, 2), "title": round(title, 2)}
        job["matched_skills"] = [s for s in core if s in c]

    jobs.sort(key=lambda x: x["score"], reverse=True)
    return jobs


def find_jobs(config: dict, seen: set = None) -> list[dict]:
    """Main entry: scrape, filter, score, return ranked jobs."""
    raw = _scrape_all(config)
    unique = _deduplicate(raw, seen or set())
    filtered = _filter_jobs(unique, config)
    return _score_jobs(filtered, config)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser(description="Find and rank remote dev jobs")
    parser.add_argument("-c", "--config", default=str(BASE_DIR / "config.yaml"))
    parser.add_argument("-o", "--output", default="output/jobs.json")
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)

    seen = set()
    history = Path(args.output).parent / "seen_jobs.json"
    if not args.no_history and history.exists():
        seen = set(json.load(open(history)))
        logger.info(f"Loaded {len(seen)} seen jobs")

    jobs = find_jobs(config, seen)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False, default=str)

    if not args.no_history:
        for j in jobs:
            if j.get("url"):
                seen.add(j["url"])
        with open(history, "w") as f:
            json.dump(list(seen), f)

    logger.info(f"Found {len(jobs)} jobs -> {args.output}")
    for j in jobs[:5]:
        logger.info(f"  [{j['score']:.0%}] {j['title']} @ {j['company']}")


if __name__ == "__main__":
    main()