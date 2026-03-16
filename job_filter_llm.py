"""
LLM-based job eligibility filter.
Uses GPT-4o-mini to check language, location, role relevance, and seniority.
"""

import json
import logging
from pathlib import Path
from openai import OpenAI
import os

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).parent

_client = None


def _get_client():
    global _client
    if _client is None:
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            from dotenv import load_dotenv
            load_dotenv()
            key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            logger.error("No OPENAI_API_KEY found")
            return None
        _client = OpenAI(api_key=key)
    return _client


def _smart_truncate(description: str, max_chars: int = 3000) -> str:
    """Truncate description but keep beginning AND end (requirements often at end)."""
    if len(description) <= max_chars:
        return description
    # Take first 2000 and last 1000 to catch requirements/language sections at bottom
    start = description[:2000]
    end = description[-1000:]
    return start + "\n[...truncated...]\n" + end


def filter_job(job: dict) -> dict:
    """
    Check if a job is eligible using LLM.
    Returns dict with 'eligible' (bool), per-check results, and reasons.
    """
    client = _get_client()
    if not client:
        # No API key — let job through
        return {"eligible": True, "error": "no_api_key"}

    # Load prompt template
    prompt_path = BASE_DIR / "prompts" / "filter.txt"
    if not prompt_path.exists():
        logger.error(f"Filter prompt not found: {prompt_path}")
        return {"eligible": True, "error": "no_prompt"}

    template = prompt_path.read_text(encoding="utf-8")

    description = job.get("description", "")
    if not description:
        # No description to analyze — let it through
        return {"eligible": True, "reason": "no_description"}

    prompt = template.format(
        title=job.get("title", "Unknown"),
        company=job.get("company", "Unknown"),
        location=job.get("location", "Unknown"),
        description=_smart_truncate(description),
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a job eligibility filter. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=500,
        )

        text = resp.choices[0].message.content.strip()
        # Clean potential markdown fences
        text = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)

        # Ensure eligible field exists
        if "eligible" not in result:
            # Derive from individual checks
            checks = [result.get("language", "YES"), result.get("location", "YES"),
                       result.get("role", "YES"), result.get("seniority", "YES")]
            result["eligible"] = all(c.upper() == "YES" for c in checks)

        return result

    except json.JSONDecodeError as e:
        logger.warning(f"LLM filter JSON parse error for '{job.get('title', '?')}': {e}")
        return {"eligible": True, "error": "json_parse"}
    except Exception as e:
        logger.warning(f"LLM filter error for '{job.get('title', '?')}': {e}")
        return {"eligible": True, "error": str(e)}


def filter_jobs(jobs: list[dict]) -> list[dict]:
    """
    Filter a list of jobs using LLM. Returns only eligible jobs.
    Logs reasons for each rejected job.
    """
    if not jobs:
        return jobs

    client = _get_client()
    if not client:
        logger.warning("LLM filter: no API key, skipping filter")
        return jobs

    logger.info(f"LLM filter: checking {len(jobs)} jobs...")
    eligible = []
    rejected = 0

    for job in jobs:
        result = filter_job(job)

        if result.get("eligible", True):
            eligible.append(job)
        else:
            rejected += 1
            reasons = []
            for check in ["language", "location", "role", "seniority"]:
                if result.get(check, "YES").upper() == "NO":
                    reasons.append(f"{check}: {result.get(f'{check}_reason', '?')}")
            reason_str = " | ".join(reasons)
            logger.info(f"  REJECTED: {job.get('title', '?')} @ {job.get('company', '?')} — {reason_str}")

        # Store filter result on job for reporting
        job["_llm_filter"] = result

    logger.info(f"LLM filter: {len(eligible)} eligible, {rejected} rejected")
    return eligible