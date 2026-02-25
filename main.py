#!/usr/bin/env python3
"""
Job Hunter - Scrape jobs, score them, tailor your resume.
Run daily. Review output. Apply manually to top matches.
"""

import os
import json
import yaml
import logging
from datetime import datetime
from pathlib import Path

from scrapers.remoteok import scrape_remoteok
from scrapers.weworkremotely import scrape_weworkremotely
from scrapers.linkedin import scrape_linkedin
from scrapers.arbeitnow import scrape_arbeitnow
from matcher import score_jobs, filter_by_language, filter_location_restricted
from tailor import tailor_resume, init_client
from resume_gen import generate_all_resumes

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Paths
BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.yaml"
OUTPUT_DIR = BASE_DIR / "output"
HISTORY_PATH = BASE_DIR / "output" / "seen_jobs.json"

# How many top jobs to tailor resumes for (overridden by config)
TOP_N_TO_TAILOR = 15
MIN_SCORE_TO_TAILOR = 0.3


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def load_seen_jobs() -> set:
    """Load previously seen job URLs to avoid duplicates across runs."""
    if HISTORY_PATH.exists():
        with open(HISTORY_PATH) as f:
            return set(json.load(f))
    return set()


def save_seen_jobs(seen: set):
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(list(seen), f)


def scrape_all(config: dict) -> list[dict]:
    """Run all scrapers and combine results."""
    search = config["search"]
    titles = search["titles"]
    locations = search["locations"]
    exclude = search["exclude_keywords"]
    
    all_jobs = []
    
    # RemoteOK - reliable, JSON API
    all_jobs.extend(scrape_remoteok(titles, exclude))
    
    # WeWorkRemotely - RSS feeds
    #all_jobs.extend(scrape_weworkremotely(titles, exclude))
    
    # LinkedIn - public search, may get rate limited
    all_jobs.extend(scrape_linkedin(titles, locations, exclude))
    
    # Arbeitnow - European remote jobs, free API
    all_jobs.extend(scrape_arbeitnow(titles, exclude))
    
    logger.info(f"Total jobs scraped: {len(all_jobs)}")
    return all_jobs


def deduplicate(jobs: list[dict], seen: set) -> list[dict]:
    """Remove duplicates by URL and previously seen jobs."""
    unique = []
    urls = set()
    
    for job in jobs:
        url = job.get("url", "")
        if not url or url in urls or url in seen:
            continue
        urls.add(url)
        unique.append(job)
    
    logger.info(f"After dedup: {len(unique)} new jobs (removed {len(jobs) - len(unique)} duplicates)")
    return unique


def generate_report(jobs: list[dict], tailored: dict, config: dict) -> str:
    """Generate a readable daily report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    lines = [
        f"# Job Hunt Report - {now}",
        f"## Found {len(jobs)} new matching jobs\n",
    ]
    
    for i, job in enumerate(jobs[:30], 1):  # Show top 30
        score = job.get("score", 0)
        breakdown = job.get("score_breakdown", {})
        
        emoji = "🟢" if score > 0.6 else "🟡" if score > 0.4 else "🔴"
        
        lines.append(f"### {emoji} #{i} — {job['title']}")
        lines.append(f"**{job['company']}** | {job['location']} | {job['source']}")
        lines.append(f"Score: **{score:.0%}** (tech:{breakdown.get('tech',0):.0%} remote:{breakdown.get('remote',0):.0%} loc:{breakdown.get('location',0):.0%} title:{breakdown.get('title',0):.0%})")
        
        if job.get("matched_skills"):
            lines.append(f"Matched: {', '.join(job['matched_skills'][:8])}")
        
        if job.get("salary_min") or job.get("salary_max"):
            sal_min = job.get("salary_min", "?")
            sal_max = job.get("salary_max", "?")
            lines.append(f"Salary: {sal_min} - {sal_max}")
        
        lines.append(f"🔗 {job['url']}")
        
        # Add tailored resume if available
        job_key = job.get("url", "")
        if job_key in tailored:
            t = tailored[job_key]
            lines.append(f"\n**Tailored Summary:** {t.get('summary', 'N/A')}")
            lines.append(f"**Highlight skills:** {', '.join(t.get('skills_to_highlight', []))}")
            
            # Show changed bullets
            for role, bullets in t.get("bullets", {}).items():
                role_name = role.replace("_", " ").title()
                lines.append(f"\n*{role_name}:*")
                for b in bullets:
                    lines.append(f"  - {b}")
        
        lines.append(f"\n{'—' * 60}\n")
    
    return "\n".join(lines)


def main():
    logger.info("=" * 50)
    logger.info("JOB HUNTER - Starting daily scan")
    logger.info("=" * 50)
    
    # Load config
    config = load_config()
    
    # Load history
    seen = load_seen_jobs()
    logger.info(f"Previously seen: {len(seen)} jobs")
    
    # Scrape all platforms
    raw_jobs = scrape_all(config)
    
    # Deduplicate
    new_jobs = deduplicate(raw_jobs, seen)
    
    if not new_jobs:
        logger.info("No new jobs found today. Try again tomorrow.")
        return
    
    # Filter out non-English/French jobs
    new_jobs = filter_by_language(new_jobs)
    
    # Filter out US-only / country-restricted jobs
    new_jobs = filter_location_restricted(new_jobs)
    
    # Score and rank
    scored_jobs = score_jobs(new_jobs, config)
    
    # Tailor resumes for top N
    tailored = {}
    has_api = init_client()
    
    tailoring_cfg = config.get("tailoring", {})
    max_tailor = tailoring_cfg.get("top_n", TOP_N_TO_TAILOR)
    min_score = tailoring_cfg.get("min_score", MIN_SCORE_TO_TAILOR)
    
    if has_api:
        top_jobs = [j for j in scored_jobs[:max_tailor] if j.get("score", 0) > min_score]
        logger.info(f"Tailoring resumes for top {len(top_jobs)} jobs (max={max_tailor}, min_score={min_score})...")
        
        for job in top_jobs:
            result = tailor_resume(job, config)
            if result:
                tailored[job["url"]] = result
    else:
        logger.warning("Skipping resume tailoring (no API key). Add OPENAI_API_KEY to .env")
    
    # Generate report
    report = generate_report(scored_jobs, tailored, config)
    
    # Generate tailored .docx resumes
    generated_resumes = generate_all_resumes(scored_jobs, tailored, config, OUTPUT_DIR)
    
    # Save report
    OUTPUT_DIR.mkdir(exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    report_path = OUTPUT_DIR / f"report_{date_str}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info(f"Report saved: {report_path}")
    
    # Save raw data
    data_path = OUTPUT_DIR / f"jobs_{date_str}.json"
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(scored_jobs, f, indent=2, default=str, ensure_ascii=False)
    logger.info(f"Raw data saved: {data_path}")
    
    # Update seen jobs
    for job in new_jobs:
        if job.get("url"):
            seen.add(job["url"])
    save_seen_jobs(seen)
    
    # Summary
    logger.info("=" * 50)
    logger.info(f"DONE. {len(new_jobs)} new jobs found, {len(tailored)} resumes tailored, {len(generated_resumes)} .docx files generated.")
    logger.info(f"Top 5 matches:")
    for j in scored_jobs[:5]:
        logger.info(f"  [{j['score']:.0%}] {j['title']} @ {j['company']} ({j['source']})")
    logger.info(f"Report: {report_path}")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()