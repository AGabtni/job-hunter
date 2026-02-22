import logging
import re

logger = logging.getLogger(__name__)


def score_jobs(jobs: list[dict], config: dict) -> list[dict]:
    """Score and rank jobs against profile."""
    profile = config["profile"]
    scoring = config["scoring"]
    search = config["search"]
    
    core_skills = [s.lower() for s in profile["core_skills"]]
    secondary_skills = [s.lower() for s in profile.get("secondary_skills", [])]
    search_titles = [t.lower() for t in search["titles"]]
    search_locations = [loc.lower() for loc in search["locations"]]
    
    scored_jobs = []
    
    for job in jobs:
        title_lower = job["title"].lower()
        desc_lower = job.get("description", "").lower()
        location_lower = job.get("location", "").lower()
        tags_lower = " ".join(t.lower() for t in job.get("tags", []))
        combined = f"{title_lower} {desc_lower} {tags_lower}"
        
        # --- Tech match (0-1) ---
        core_matches = sum(1 for s in core_skills if s in combined)
        secondary_matches = sum(1 for s in secondary_skills if s in combined)
        total_skills = len(core_skills) + len(secondary_skills)
        
        # Core skills worth more
        tech_score = 0
        if total_skills > 0:
            tech_score = min(1.0, (core_matches * 1.5 + secondary_matches * 0.5) / (len(core_skills) * 0.4))
        
        # --- Remote match (0-1) ---
        remote_keywords = ["remote", "anywhere", "worldwide", "work from home", "wfh", "distributed", "télétravail"]
        remote_score = 1.0 if any(kw in combined or kw in location_lower for kw in remote_keywords) else 0.2
        
        # --- Location match (0-1) ---
        location_score = 0.5  # Default for unclear location
        if any(loc in location_lower for loc in search_locations):
            location_score = 1.0
        elif "united states" in location_lower or "us only" in location_lower:
            location_score = 0.1  # Likely can't work from Tunisia
        
        # --- Title match (0-1) ---
        title_score = 0.3  # Base score if it passed initial filter
        for search_title in search_titles:
            if search_title in title_lower:
                title_score = 1.0
                break
            # Partial match
            title_words = set(search_title.split())
            job_title_words = set(title_lower.split())
            overlap = len(title_words & job_title_words)
            if overlap >= 2:
                title_score = max(title_score, 0.7)
        
        # --- Weighted total ---
        total_score = (
            tech_score * scoring["tech_match"]
            + remote_score * scoring["remote_match"]
            + location_score * scoring["location_match"]
            + title_score * scoring["title_match"]
        )
        
        job["score"] = round(total_score, 3)
        job["score_breakdown"] = {
            "tech": round(tech_score, 2),
            "remote": round(remote_score, 2),
            "location": round(location_score, 2),
            "title": round(title_score, 2),
        }
        job["matched_skills"] = [s for s in core_skills if s in combined]
        
        scored_jobs.append(job)
    
    # Sort by score descending
    scored_jobs.sort(key=lambda x: x["score"], reverse=True)
    
    logger.info(f"Scored {len(scored_jobs)} jobs. Top score: {scored_jobs[0]['score'] if scored_jobs else 'N/A'}")
    
    return scored_jobs
