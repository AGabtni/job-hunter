import os
import json
import re
import logging
from collections import Counter
from openai import OpenAI
from dotenv import load_dotenv
from resume_gen import _clean_job_title

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


def _extract_top_keywords(job_desc: str, n: int = 20) -> list[tuple[str, int]]:
    """Extract the most frequently mentioned technical/meaningful keywords from job description."""
    stop_words = {
        "the", "and", "for", "are", "but", "not", "you", "all", "can", "her", "was",
        "one", "our", "out", "has", "have", "been", "from", "they", "with", "this",
        "that", "will", "your", "their", "about", "would", "there", "these", "other",
        "into", "more", "some", "such", "than", "them", "then", "what", "when", "which",
        "who", "how", "each", "she", "two", "way", "its", "may", "also", "must",
        "work", "working", "ability", "strong", "experience", "team", "role", "looking",
        "join", "company", "position", "candidate", "ideal", "required", "preferred",
        "including", "using", "etc", "well", "good", "great", "should", "could",
        "based", "help", "make", "like", "need", "new", "high", "best", "ensure",
        "across", "within", "part", "take", "year", "years", "day", "time",
    }
    
    words = re.findall(r'[a-zA-Z\+\#\.]{3,}', job_desc.lower())
    words = [w for w in words if w not in stop_words]
    counts = Counter(words)
    return counts.most_common(n)


def tailor_resume(job: dict, config: dict) -> dict | None:
    """Tailor resume bullets AND skills section for a specific job using OpenAI."""
    if client is None:
        if not init_client():
            return None
    
    base_resume = config["base_resume"]
    profile = config["profile"]
    
    job_desc = job.get("description", "No description available")
    job_title = job.get("title", "")
    company = job.get("company", "")
    matched_skills = job.get("matched_skills", [])
    
    # Clean the title before sending to GPT
    clean_title = _clean_job_title(job_title)
    
    # Extract top keywords with frequency for GPT awareness
    top_keywords = _extract_top_keywords(job_desc)
    keyword_freq_str = ", ".join(f"{kw}({count}x)" for kw, count in top_keywords if count >= 2)
    
    prompt = f"""You are a resume optimization expert. Tailor this resume for the specific job posting.
Your #1 goal: MAXIMIZE keyword overlap with the job description to pass ATS filters.

JOB:
- Title: {clean_title}
- Original posting title: {job_title}
- Company: {company}
- Description: {job_desc[:2000]}

HIGH-FREQUENCY JOB KEYWORDS (must appear in resume):
{keyword_freq_str}

CANDIDATE'S FULL SKILL INVENTORY (only use skills from this list - do NOT invent skills):
- Programming: JavaScript, TypeScript, Python, Java, C++, C#, SQL, PHP
- Frontend: React.js, HTML, CSS, Tailwind, Bootstrap, Responsive Design, WordPress, Drupal, Webflow, WooCommerce
- Backend: Node.js, Express, Spring Boot, REST APIs, .NET, PHP
- Databases: PostgreSQL, MongoDB, SQL Server, MySQL
- Cloud & DevOps: Azure, Docker, CI/CD, Git, SAP Cloud Platform
- Tools: GitHub Copilot, Jira, Agile/Scrum, Figma
- CMS/Web: WordPress, Drupal, WooCommerce, SEO, Web Accessibility, Google Analytics
- Spoken: French (C2), English (C2)

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
3. NEVER remove numbers or percentages from bullets. Every metric (20%, 30%, 50+, 8+, etc.) MUST appear in the rewritten version
4. EVERY role MUST have EXACTLY 3 bullets. No more, no less
5. If a keyword appears multiple times in the job description, try to mention it in MULTIPLE places across the resume (summary, skills, AND bullets)
6. The summary MUST start with the EXACT clean job title "{clean_title}". Example: "{clean_title} with 5+ years of experience..." This is critical for ATS keyword matching.
7. For the skills section: reorder and regroup skills to put JOB-RELEVANT skills FIRST. Add any skills from the candidate's inventory that match the job but aren't in the default skills. Remove skills irrelevant to this specific job to make room
8. Use strong action verbs
9. Use EXACTLY these bullet keys: city_of_gatineau, precision_os, syntax, uottawa

Return a JSON object with EXACTLY this structure:
{{
  "summary": "A 2-3 sentence professional summary tailored for this role",
  "skills": {{
    "Languages": "skill1, skill2, skill3",
    "Frontend": "skill1, skill2, skill3",
    "Backend": "skill1, skill2, skill3",
    "Databases": "skill1, skill2",
    "Cloud & DevOps": "skill1, skill2, skill3",
    "Tools": "skill1, skill2, skill3",
    "Spoken Languages": "French (Fluent, C2), English (Fluent, C2)"
  }},
  "bullets": {{
    "city_of_gatineau": ["bullet1", "bullet2", "bullet3"],
    "precision_os": ["bullet1", "bullet2", "bullet3"],
    "syntax": ["bullet1", "bullet2", "bullet3"],
    "uottawa": ["bullet1", "bullet2", "bullet3"]
  }},
  "skills_to_highlight": ["skill1", "skill2", "skill3"]
}}

CRITICAL: 
- Each role MUST have EXACTLY 3 bullets
- Use EXACTLY the keys shown above
- Skills section must reflect THIS job's requirements, not be generic
- If job mentions WordPress 5 times, WordPress must appear in skills AND at least one bullet
Return ONLY valid JSON, no markdown, no backticks."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a resume expert. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=2500,
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