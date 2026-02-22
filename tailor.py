import os
import json
import logging
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

client = None


def init_client():
    global client
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "sk-your-key-here":
        logger.warning("No OpenAI API key set. Resume tailoring will be skipped.")
        return False
    client = OpenAI(api_key=api_key)
    return True


def tailor_resume(job: dict, config: dict) -> dict | None:
    """Tailor resume bullets for a specific job using OpenAI."""
    if client is None:
        if not init_client():
            return None
    
    base_resume = config["base_resume"]
    profile = config["profile"]
    
    # Build the prompt
    all_bullets = []
    for role_key, bullets in base_resume["bullets"].items():
        all_bullets.extend(bullets)
    
    job_desc = job.get("description", "No description available")
    job_title = job.get("title", "")
    company = job.get("company", "")
    matched_skills = job.get("matched_skills", [])
    
    prompt = f"""You are a resume optimization expert. Tailor the following resume bullets for this specific job posting.

JOB:
- Title: {job_title}
- Company: {company}
- Description: {job_desc[:1500]}

CANDIDATE PROFILE:
- Name: {profile['name']}
- {profile['years_experience']}+ years experience
- Languages: {', '.join(profile['languages'])}
- Skills matching this job: {', '.join(matched_skills)}

CURRENT RESUME BULLETS:
{chr(10).join(f'- {b}' for b in all_bullets)}

INSTRUCTIONS:
1. Rewrite ONLY the bullets that can be improved for this specific job
2. Keep the same factual content - do NOT fabricate metrics or experiences
3. Emphasize skills and technologies mentioned in the job description
4. If a bullet is already good as-is, keep it unchanged
5. Keep bullets concise (1-2 lines each)
6. Use strong action verbs

Return a JSON object with this structure:
{{
  "summary": "A 2-sentence professional summary tailored for this role",
  "bullets": {{
    "city_of_gatineau": ["bullet1", "bullet2", "bullet3"],
    "precision_os": ["bullet1", "bullet2", "bullet3", "bullet4"],
    "syntax": ["bullet1", "bullet2", "bullet3", "bullet4"],
    "uottawa": ["bullet1", "bullet2", "bullet3"]
  }},
  "skills_to_highlight": ["skill1", "skill2", "skill3"]
}}

Return ONLY valid JSON, no markdown, no backticks."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a resume expert. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=2000,
        )
        
        content = response.choices[0].message.content.strip()
        
        # Clean potential markdown wrapping
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        result = json.loads(content)
        
        logger.info(f"Tailored resume for: {job_title} at {company}")
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenAI response as JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return None
