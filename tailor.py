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
    
    prompt = f"""You are a resume optimization expert. Tailor the following resume bullets for this specific job posting. Your goal is to MAXIMIZE keyword overlap with the job description while keeping content truthful.

JOB:
- Title: {job_title}
- Company: {company}
- Description: {job_desc[:1500]}

CANDIDATE PROFILE:
- Name: {profile['name']}
- {profile['years_experience']}+ years experience
- Languages: {', '.join(profile['languages'])}
- Skills matching this job: {', '.join(matched_skills)}

CURRENT RESUME BULLETS BY ROLE:
[city_of_gatineau]
{chr(10).join(f'- {b}' for b in base_resume['bullets'].get('city_of_gatineau', []))}

[precision_os]
{chr(10).join(f'- {b}' for b in base_resume['bullets'].get('precision_os', []))}

[syntax]
{chr(10).join(f'- {b}' for b in base_resume['bullets'].get('syntax', []))}

[uottawa]
{chr(10).join(f'- {b}' for b in base_resume['bullets'].get('uottawa', []))}

INSTRUCTIONS:
1. Rewrite bullets to emphasize skills and technologies from the job description
2. Keep the same factual content - do NOT fabricate metrics or experiences
3. NEVER remove numbers or percentages from bullets. Every metric (20%, 30%, 50+, 8+, etc.) from the original MUST appear in the rewritten version.
4. EVERY role MUST have EXACTLY 3 bullets. No more, no less.
5. Work as many keywords from the job description into the bullets as possible without making them sound forced
6. The summary must be a single paragraph (2-3 sentences) that naturally includes key terms from the job description
7. Use strong action verbs
8. Use EXACTLY these keys: city_of_gatineau, precision_os, syntax, uottawa

Return a JSON object with EXACTLY this structure:
{{
  "summary": "A 2-3 sentence professional summary paragraph tailored for this role, incorporating key terms from the job description",
  "bullets": {{
    "city_of_gatineau": ["bullet1", "bullet2", "bullet3"],
    "precision_os": ["bullet1", "bullet2", "bullet3"],
    "syntax": ["bullet1", "bullet2", "bullet3"],
    "uottawa": ["bullet1", "bullet2", "bullet3"]
  }},
  "skills_to_highlight": ["skill1", "skill2", "skill3"]
}}

CRITICAL: Each role MUST have EXACTLY 3 bullets. Use EXACTLY the keys shown above.
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