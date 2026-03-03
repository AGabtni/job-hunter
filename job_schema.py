"""
Standard Job Schema — shared across all modules.
Every module reads/writes jobs using this format.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def create_job(
    title="", company="", location="", description="", url="", source="",
    tags=None, salary="", date="", score=0.0, score_breakdown=None, matched_skills=None,
) -> dict:
    """Create a job dict with the standard schema."""
    return {
        "title": title, "company": company, "location": location,
        "description": description, "url": url, "source": source,
        "tags": tags or [], "salary": salary, "date": date,
        "score": score, "score_breakdown": score_breakdown or {},
        "matched_skills": matched_skills or [],
    }


def validate_job(job: dict) -> dict:
    """Ensure a job dict has all required fields. Fills missing with defaults."""
    defaults = create_job()
    for key, val in defaults.items():
        if key not in job:
            job[key] = val
    return job


def load_jobs(filepath: str | Path) -> list[dict]:
    """Load jobs from JSON file. Handles single job or list."""
    path = Path(filepath)
    if not path.exists():
        logger.error(f"Job file not found: {filepath}")
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [data]
    return [validate_job(j) for j in data]


def save_jobs(jobs: list[dict], filepath: str | Path):
    """Save jobs to JSON file."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, default=str, ensure_ascii=False)
    logger.info(f"Saved {len(jobs)} jobs to {filepath}")