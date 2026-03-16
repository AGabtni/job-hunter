#!/usr/bin/env python3
"""
Job Hunter Pipeline — Orchestrates all modules.

Usage:
    python main.py                                    # full pipeline: scrape → tailor → generate
    python main.py --urls URL1 URL2                   # scrape specific URLs → tailor → generate
    python main.py --jobs jobs.json                   # skip scraping, use existing jobs.json
"""

import logging
import argparse
import yaml
import json
from datetime import datetime
from pathlib import Path

# Load .env ONCE at startup — all modules inherit via os.environ
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from job_schema import save_jobs, load_jobs

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).parent


def _load_config(config_path: str = None) -> dict:
    path = Path(config_path) if config_path else BASE_DIR / "config.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _generate_report(jobs: list[dict], output_dir: Path):
    """Save a readable daily report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# Job Hunt Report - {now}", f"## {len(jobs)} jobs found\n"]

    for i, job in enumerate(jobs[:30], 1):
        score = job.get("score", 0)
        bd = job.get("score_breakdown", {})
        emoji = "🟢" if score > 0.6 else "🟡" if score > 0.4 else "🔴"
        lines.append(f"### {emoji} #{i} — {job['title']}")
        lines.append(f"**{job['company']}** | {job['location']} | {job['source']}")
        lines.append(f"Score: **{score:.0%}** (tech:{bd.get('tech',0):.0%} remote:{bd.get('remote',0):.0%} loc:{bd.get('location',0):.0%} title:{bd.get('title',0):.0%})")
        if job.get("matched_skills"):
            lines.append(f"Matched: {', '.join(job['matched_skills'][:8])}")
        lines.append(f"🔗 {job['url']}")
        lines.append(f"\n{'—' * 60}\n")

    report_path = output_dir / f"report_{datetime.now().strftime('%Y-%m-%d')}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.info(f"Report: {report_path}")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

    parser = argparse.ArgumentParser(description="Job Hunter Pipeline")
    parser.add_argument("--urls", nargs="+", help="Scrape specific job URLs instead of searching")
    parser.add_argument("--jobs", help="Path to existing jobs.json (skip scraping)")
    parser.add_argument("-c", "--config", default=None, help="Path to config.yaml")
    parser.add_argument("-o", "--output", default="output", help="Output directory")
    parser.add_argument("--no-history", action="store_true", help="Ignore seen_jobs.json")
    args = parser.parse_args()

    config = _load_config(args.config)
    output_dir = BASE_DIR / args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 50)
    logger.info("JOB HUNTER PIPELINE")
    logger.info("=" * 50)

    # Step 1: Get jobs
    if args.jobs:
        # Use existing jobs file
        jobs = load_jobs(args.jobs)
        logger.info(f"Loaded {len(jobs)} jobs from {args.jobs}")
    elif args.urls:
        # Scrape specific URLs
        from job_scraper import scrape_job_urls
        jobs = scrape_job_urls(args.urls)
        logger.info(f"Scraped {len(jobs)} jobs from URLs")
    else:
            # Full scrape pipeline
            from job_finder import find_jobs

            seen = set()
            history_path = output_dir / "seen_jobs.json"
            if not args.no_history and history_path.exists():
                with open(history_path) as f:
                    seen = set(json.load(f))
                logger.info(f"Previously seen: {len(seen)} jobs")

            jobs = find_jobs(config, seen=seen)

            # Update seen history
            if not args.no_history and jobs:
                for j in jobs:
                    if j.get("url"):
                        seen.add(j["url"])
                with open(history_path, "w") as f:
                    json.dump(list(seen), f)

    if not jobs:
        logger.info("No jobs found. Exiting.")
        return

    # Save jobs JSON
    save_jobs(jobs, output_dir / f"jobs_{datetime.now().strftime('%Y-%m-%d')}.json")

    # Step 2: Generate resumes
    from resume_generator import generate_all
    resumes_dir = output_dir / "resumes"
    generated = generate_all(jobs, config, resumes_dir)

    # Step 3: Report
    _generate_report(jobs, output_dir)

    # Summary
    logger.info("=" * 50)
    logger.info(f"DONE. {len(jobs)} jobs, {len(generated)} resumes generated.")
    if jobs:
        logger.info("Top 5:")
        for j in jobs[:5]:
            logger.info(f"  [{j.get('score', 0):.0%}] {j['title']} @ {j['company']}")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()