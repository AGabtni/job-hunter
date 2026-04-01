# Job Hunter - Automated Job Scraping & Resume Tailoring

End-to-end job search automation: scrapes remote dev jobs, filters by eligibility, scores by relevance, and generates ATS-optimized tailored resumes.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# 3. Edit config.yaml with your profile and preferences

# 4. Run full pipeline (scrape → filter → score → generate resumes)
python main.py
```

Output: `output/jobs_YYYY-MM-DD.json` + `output/resumes/` + `output/report_YYYY-MM-DD.md`

---

## Modules Overview

| Module | Purpose | Standalone? |
|--------|---------|-------------|
| `main.py` | Full pipeline orchestration | ✅ Entry point |
| `job_finder.py` | Scrape multiple boards, filter, score | ✅ Yes |
| `job_scraper.py` | Scrape single job URL | ✅ Yes |
| `resume_generator.py` | GPT-based resume tailoring + ATS retry | ✅ Yes |
| `ats_checker.py` | Validate resume ATS compatibility | ✅ Yes |
| `job_filter_llm.py` | GPT-based eligibility filter | Library only |
| `job_schema.py` | Job data structure utilities | Library only |
| `config.yaml` | User config (profile, preferences) | Config file |

---

## Module Documentation

### 1. `main.py` — Full Pipeline

**Purpose:** Orchestrates the entire workflow: scrape → filter → score → tailor → generate resumes.

**Usage:**
```bash
# Full pipeline (recommended)
python main.py

# Use existing jobs.json (skip scraping)
python main.py --jobs output/jobs_2026-03-15.json

# Scrape specific job URLs only
python main.py --urls https://linkedin.com/jobs/view/123 https://remoteok.com/job/xyz

# Custom output directory
python main.py -o my_output

# Skip seen jobs history
python main.py --no-history

# Custom config file
python main.py -c my_config.yaml
```

**What it does:**
1. Loads config from `config.yaml`
2. Scrapes jobs from 9 job boards (or uses provided URLs/file)
3. Deduplicates against `seen_jobs.json` history
4. Filters by language, location, company exclusions
5. **LLM Filter** (optional): Uses GPT to check language requirements, location eligibility, role type, seniority
6. Scores jobs by tech match, remote, location, title
7. Generates tailored resumes for top N jobs (config: `tailoring.top_n`)
8. Saves: `jobs_YYYY-MM-DD.json`, `report_YYYY-MM-DD.md`, `output/resumes/`

**Output Structure:**
```
output/
├── jobs_2026-03-15.json          # All scraped jobs with scores
├── report_2026-03-15.md          # Human-readable report
├── seen_jobs.json                # History to avoid duplicates
└── resumes/
    ├── CompanyA_JobTitle/
    │   ├── AG_Resume.docx        # Tailored resume
    │   ├── ats_report.txt        # ATS validation
    │   └── job_link.txt          # Job URL
    └── CompanyB_JobTitle/
        └── ...
```

---

### 2. `job_finder.py` — Multi-Board Scraper

**Purpose:** Scrapes 9 job boards, deduplicates, filters, and scores jobs.

**Standalone Usage:**
```bash
# Full scrape (saves to output/jobs.json)
python job_finder.py

# Custom output
python job_finder.py -o my_jobs.json

# Skip seen_jobs.json history
python job_finder.py --no-history

# Custom config
python job_finder.py -c my_config.yaml
```

**Scrapers Included:**
- RemoteOK
- LinkedIn (guest mode, 3 pages per query)
- Arbeitnow
- Remotive
- Jobicy
- Himalayas
- WorkingNomads
- WeWorkRemotely (not active in current config)
- Indeed (not active in current config)

**Filtering Pipeline:**
1. **Deduplication** by URL and company+title signature
2. **Language detection** (skips German, Spanish, Portuguese, Dutch, Italian job descriptions)
3. **Location restrictions** (skips "US only", "EU work permit required", hybrid/on-site)
4. **Company exclusions** (config: `search.exclude_companies`)
5. **Keyword exclusions** (config: `search.exclude_keywords` — senior, principal, blockchain, mobile, etc.)
6. **Blocked countries** (config: `search.blocked_countries` — low-salary markets)
7. **LLM Filter** (if `search.llm_filter: true`): GPT checks language, location, role, seniority

**Scoring:**
Jobs are scored 0-1 based on:
- **Tech match** (35%): How many of your `profile.core_skills` appear in the job
- **Remote match** (25%): "remote", "worldwide", "work from home" keywords
- **Location match** (20%): Whether location is in your `search.locations`
- **Title match** (20%): Overlap with `search.titles`

**Output:** `jobs.json` with schema:
```json
{
  "title": "Full-Stack Developer",
  "company": "Acme Inc",
  "location": "Remote (Worldwide)",
  "description": "...",
  "url": "https://...",
  "source": "LinkedIn",
  "tags": ["react", "node"],
  "salary": "USD 80k-120k",
  "date": "2026-03-15",
  "score": 0.78,
  "score_breakdown": {"tech": 0.85, "remote": 1.0, "location": 0.7, "title": 0.8},
  "matched_skills": ["javascript", "react", "node.js"]
}
```

---

### 3. `job_scraper.py` — Single URL Scraper

**Purpose:** Fetch a single job posting URL and return standardized JSON.

**Usage:**
```bash
# Scrape a job URL (prints to stdout)
python job_scraper.py https://linkedin.com/jobs/view/12345

# Save to file
python job_scraper.py https://remoteok.com/job/xyz -o job.json
```

**Supported Sites:**
- LinkedIn
- RemoteOK
- Remotive
- WeWorkRemotely
- Arbeitnow
- Generic (fallback parser for unknown sites)

**Use Case:** When you find a job manually and want to add it to your pipeline.

**Output:** Same schema as `job_finder.py`, but for a single job.

---

### 4. `resume_generator.py` — AI Resume Tailoring

**Purpose:** Generates tailored .docx resumes using GPT-4o-mini with ATS retry loop.

**Standalone Usage:**
```bash
# Generate from single job
python resume_generator.py output/jobs.json

# Generate from jobs array, top 5 only
python resume_generator.py output/jobs.json --top 5

# Custom output directory
python resume_generator.py job.json -o my_resumes/

# Skip ATS retry loop (faster, lower quality)
python resume_generator.py job.json --no-ats-retry

# Custom config
python resume_generator.py job.json -c my_config.yaml
```

**How It Works:**

1. **GPT Tailoring:**
   - Reads prompts from `prompts/tailor.txt` and `prompts/system.txt`
   - Extracts top keywords from job description (frequency-based)
   - Asks GPT to:
     - Write a job-specific summary starting with the exact job title
     - Reorder skills section to prioritize job-relevant tech
     - Lightly rephrase bullet points to include job keywords (without changing facts)
   - **Rules for GPT:**
     - NEVER fabricate experience
     - Skills go in summary/skills section, NOT invented in bullets
     - Keep all original metrics (20%, 50+, 8+, etc.)
     - Each role: exactly 3 bullets

2. **Resume Template:**
   - If `tailoring.template` set in config → fills `Template-Resume-Placeholders.docx`
   - Else → builds from scratch with proper formatting

3. **ATS Retry Loop:**
   - Generates resume
   - Runs `ats_checker.py` to get keyword match %
   - If match % < `resume_generator.min_keyword_pct` (default: 45%):
     - Extracts missing keywords
     - Retries GPT with emphasis on missing keywords
     - Repeats up to `resume_generator.max_retries` times (default: 3)

**Output:**
```
output/resumes/
└── CompanyName_JobTitle/
    ├── AG_Resume.docx       # Tailored resume
    ├── ats_report.txt       # ATS validation results
    └── job_link.txt         # Job title, company, URL
```

**Config Options:**
```yaml
tailoring:
  top_n: 15                    # How many jobs to generate resumes for
  min_score: 0.3               # Only jobs with score >= this
  template: "path/to/template.docx"  # Optional: use your own template

resume_generator:
  max_retries: 3               # ATS retry attempts
  min_keyword_pct: 45          # Target keyword match %
```

---

### 5. `ats_checker.py` — Resume Validator

**Purpose:** Validates .docx resumes for ATS compatibility and keyword match.

**Standalone Usage:**
```bash
# Check resume (no job description)
python ats_checker.py path/to/resume.docx

# Check against job description
python ats_checker.py resume.docx --job-description "paste full job description here"

# Check against job description file
python ats_checker.py resume.docx --job-file job_description.txt

# Check against job JSON
python ats_checker.py resume.docx --job-json output/jobs.json

# JSON output (for scripting)
python ats_checker.py resume.docx --json
```

**Checks Performed:**

1. **File Format:** Valid .docx, not PDF/HTML
2. **Text Extractability:** Can extract plain text (ATS requirement)
3. **Fonts:** Uses ATS-safe fonts (Calibri, Arial, Times New Roman, etc.)
4. **Tables:** Warns if tables used for layout (ATS often can't parse)
5. **Images:** Flags images (ATS can't read text in images)
6. **Headers/Footers:** Warns if important content in headers/footers
7. **Text Boxes:** Flags text boxes (ATS ignores these completely)
8. **Sections:** Checks for expected sections (experience, education, skills, contact)
9. **Special Characters:** Warns about fancy Unicode that might break parsing
10. **File Size:** Flags if > 5MB (some ATS reject large files)
11. **Keyword Match:** If job description provided, calculates overlap %

**Output Format:**
```
========================================
ATS COMPATIBILITY REPORT
========================================
Resume: path/to/resume.docx
Overall Score: 85%
ATS Ready: ✅ YES

File Format: ✅ PASS
Text Extraction: ✅ PASS
Fonts: ⚠️  WARNING
  - Using uncommon font: Papyrus
  
Keyword Match: 67%
  Matched: javascript, react, node.js, typescript, python
  Missing: graphql, kubernetes, terraform
  
Recommendations:
  1. Replace Papyrus with Calibri or Arial
  2. Add missing keywords to skills section
```

**Use Case:** Run this before submitting any resume to ensure ATS compatibility.

---

### 6. `job_filter_llm.py` — GPT Eligibility Filter (Library)

**Purpose:** Uses GPT-4o-mini to intelligently filter jobs by language requirements, location eligibility, role type, and seniority.

**Not Standalone** — called by `job_finder.py` if `search.llm_filter: true`

**What It Checks:**

1. **Language:** Does the job REQUIRE fluency in German/Russian/Polish/etc? (not just prefer)
2. **Location:** Can candidate work this job?
   - Considers: visa sponsorship offers, EOR services (Deel, Remote.com), sponsorship-friendly countries
   - Geography logic: Canada = North America, Tunisia = Africa/MENA
   - When in doubt → **approves** (better false positive than false negative)
3. **Role:** Is this an IC software development role? (not PM, designer, QA-only, DevOps-only)
4. **Seniority:** Can someone with 5 years experience apply? (not staff/principal 8+ years only)

**Prompt Location:** `prompts/filter.txt`

**Why It Exists:** Regex filters miss nuance. GPT can understand:
- "German fluency preferred" (OK) vs "German C1 required" (reject)
- "Remote worldwide" (OK) vs "Remote, must already have US work authorization" (reject)
- "Senior Software Engineer (3+ years)" (OK) vs "Principal Engineer (10+ years)" (reject)

**Performance:** ~500 tokens per job, ~$0.001 per job at GPT-4o-mini rates.

---

### 7. `job_schema.py` — Job Data Utilities (Library)

**Purpose:** Standardized job data structure and helper functions.

**Functions:**
```python
from job_schema import create_job, validate_job, load_jobs, save_jobs

# Create a job
job = create_job(
    title="Developer",
    company="Acme",
    location="Remote",
    description="...",
    url="https://...",
    source="LinkedIn"
)

# Load from file
jobs = load_jobs("jobs.json")  # Handles both single job and array

# Save to file
save_jobs(jobs, "output.json")
```

**Standard Fields:**
- `title`, `company`, `location`, `description`, `url`, `source`
- `tags`, `salary`, `date`
- `score`, `score_breakdown`, `matched_skills` (added by scorer)

---

## Configuration (`config.yaml`)

### Search Settings
```yaml
search:
  titles:
    - "full stack developer"
    - "fullstack developer"
    - "frontend developer"
    # ... list of job titles to search for
  
  locations:
    - "remote"
    - "canada"
    - "tunisia"
    # ... acceptable work locations
  
  exclude_keywords:
    - "senior staff"
    - "principal"
    - "blockchain"
    # ... titles/keywords to skip
  
  exclude_companies:
    - "twine"
    - "BairesDev"
    # ... recruiting agencies to skip
  
  blocked_countries:
    - "philippines"
    - "india"
    # ... low-salary markets to skip
  
  min_salary_cad: 40000
  max_age_days: 7          # Only jobs posted within this window
  llm_filter: true         # Enable GPT-based eligibility filter
```

### Scoring Weights
```yaml
scoring:
  tech_match: 0.35       # How important is tech stack match
  remote_match: 0.25     # How important is "remote" keyword
  location_match: 0.20   # How important is location match
  title_match: 0.20      # How important is title match
```

### Resume Generation
```yaml
tailoring:
  top_n: 15                           # Generate resumes for top 15 jobs
  min_score: 0.3                      # Only if score >= 0.3
  template: "Template-Resume.docx"    # Optional: your template

resume_generator:
  max_retries: 3           # ATS retry attempts
  min_keyword_pct: 45      # Target keyword match %
```

### Your Profile
```yaml
profile:
  name: "Your Name"
  email: "you@example.com"
  linkedin: "https://linkedin.com/in/yourname"
  years_experience: 5
  languages:
    - "English (C2)"
    - "French (C2)"
  core_skills:
    - "javascript"
    - "typescript"
    - "react"
    - "node.js"
    # ... your tech stack
  secondary_skills:
    - "docker"
    - "ci/cd"
    # ... nice-to-have skills

base_resume:
  current_role: "Full-Stack Developer | Company | Date"
  bullets:
    current_company:
      - "Bullet 1 with metrics (30%)"
      - "Bullet 2 with metrics (20%)"
      - "Bullet 3 with metrics (50+)"
    previous_company:
      - "Bullet 1"
      - "Bullet 2"
      - "Bullet 3"
    # ... 4-5 roles with 3 bullets each
```

---

## Prompt Engineering (`prompts/`)

All GPT prompts are externalized for easy editing:

| File | Purpose |
|------|---------|
| `system.txt` | System message for resume tailoring |
| `tailor.txt` | Main resume tailoring instructions |
| `retry.txt` | Additional instructions for ATS retry |
| `filter.txt` | Job eligibility filter instructions |
| `ats_manual_tweaks.txt` | Manual ATS optimization guide (not used by code) |

**Why External?** Easier to:
- Version control prompt changes
- A/B test different prompts
- Debug GPT behavior
- Share prompts with team

**How to Edit:**
1. Open the relevant `.txt` file in `prompts/`
2. Edit the prompt (use `{variable}` placeholders)
3. Save — next run picks up changes immediately

---

## Environment Variables (`.env`)

```bash
# Required
OPENAI_API_KEY=sk-...

# Optional
LINKEDIN_LI_AT=...  # LinkedIn session cookie (not currently used)
```

---

## Typical Workflow

### Daily Job Hunt
```bash
# Morning: run full pipeline
python main.py

# Review: output/report_2026-03-15.md
# Check: output/resumes/ for generated resumes
# Apply: submit resumes from output/resumes/CompanyName_JobTitle/
```

### Manual Job URL
```bash
# Found a job manually? Add it:
python job_scraper.py https://example.com/job/123 -o manual_job.json

# Generate resume for it:
python resume_generator.py manual_job.json
```

### ATS Debugging
```bash
# Check your resume before submitting:
python ats_checker.py my_resume.docx --job-file job_description.txt

# Fix issues, re-check:
python ats_checker.py my_resume_v2.docx --job-file job_description.txt
```

### Testing Filters
```bash
# Disable LLM filter to see what regex catches:
# Set search.llm_filter: false in config.yaml
python job_finder.py

# Compare with LLM filter enabled:
# Set search.llm_filter: true
python job_finder.py
```

---

## Troubleshooting

### "No jobs found"
- Check `config.yaml` → `search.titles` and `search.locations` are not too restrictive
- Try `python job_finder.py --no-history` to ignore duplicates
- Check `search.exclude_keywords` — might be too aggressive

### "LLM filter rejecting everything"
- Check OpenAI API key in `.env`
- Review `prompts/filter.txt` — might be too strict
- Disable with `search.llm_filter: false` to debug

### "Resume doesn't match job"
- Check `prompts/tailor.txt` — adjust instructions
- Lower `resume_generator.min_keyword_pct` if retries hit limit
- Add missing tech to `profile.core_skills` if you know it

### "LinkedIn rate limited"
- LinkedIn guest API has limits (~50-100 jobs per run)
- Add delays between runs (done automatically)
- Consider reducing search queries in linkedin.py

### "ATS checker fails"
- Ensure `python-docx` installed: `pip install python-docx`
- Resume must be .docx, not .doc or .pdf
- Check file isn't corrupted

---

## Advanced Usage

### Custom Scrapers
Add a new scraper in `scrapers/`:
```python
# scrapers/mynewboard.py
def scrape_mynewboard(titles, exclude_keywords, blocked_countries=None):
    jobs = []
    # ... scraping logic ...
    return jobs  # List of dicts with standard schema
```

Register in `job_finder.py`:
```python
from scrapers.mynewboard import scrape_mynewboard
# ...
all_jobs.extend(scrape_mynewboard(titles, exclude))
```

### Custom Scoring
Edit `job_finder.py` → `_score_jobs()` function to change ranking logic.

### Template Customization
1. Copy `Template-Resume-Placeholders.docx`
2. Edit in Word, use placeholders: `{{NAME}}`, `{{TITLE}}`, `{{SUMMARY}}`, etc.
3. Set `tailoring.template: "MyTemplate.docx"` in config
4. See `resume_generator.py` → `_fill_template()` for full list of placeholders

---

## Architecture

```
┌─────────────┐
│  main.py    │  Orchestrator
└──────┬──────┘
       │
       ├─→ job_finder.py ─────┬─→ scrapers/*.py (9 boards)
       │                      ├─→ job_filter_llm.py (GPT filter)
       │                      └─→ job_schema.py (data utils)
       │
       ├─→ resume_generator.py ──┬─→ prompts/*.txt (GPT prompts)
       │                         └─→ ats_checker.py (validation)
       │
       └─→ output/
           ├── jobs_*.json
           ├── report_*.md
           └── resumes/
```

---

## Contributing

When adding features:
1. Update module docstrings with standalone examples
2. Add CLI arguments with `--help` support
3. Update this README
4. Test standalone usage of affected modules

---

## License

MIT (or your license)
