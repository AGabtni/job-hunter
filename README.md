# Job Hunter — Automated Job Search & Resume Pipeline

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o--mini-green.svg)](https://openai.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

End-to-end automation that scrapes 7 job boards, applies multi-layer filtering (keyword + regex + LLM), scores by relevance, and generates ATS-optimized tailored resumes — fully configurable via YAML.

> I built this to automate my own job search. It runs daily, finds ~300 listings, filters down to ~15 relevant ones, and generates tailored resumes for each — what used to take hours now takes minutes.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         main.py                                 │
│                    Pipeline Orchestrator                         │
└──────────┬──────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────┐     ┌──────────────────────────────────┐
│   job_finder.py     │────▶│         7 Scrapers               │
│   Scrape + Filter   │     │  LinkedIn · RemoteOK · Himalayas │
│   + Score           │     │  Remotive · Jobicy · Arbeitnow   │
│                     │     │  WorkingNomads                    │
└──────────┬──────────┘     └──────────────────────────────────┘
           │
           ▼
┌─────────────────────┐     ┌──────────────────────────────────┐
│  Filtering Pipeline │     │  1. Dedup (URL + company)        │
│                     │────▶│  2. Keyword exclusion            │
│                     │     │  3. Location/language regex       │
│                     │     │  4. Blocked countries             │
│                     │     │  5. Company blacklist             │
│                     │     │  6. LLM eligibility (GPT-4o)     │
└──────────┬──────────┘     └──────────────────────────────────┘
           │
           ▼
┌─────────────────────┐     ┌──────────────────────────────────┐
│ resume_generator.py │────▶│  GPT tailors resume per job      │
│ Tailor + Generate   │     │  ATS retry loop (3 attempts)     │
│                     │     │  Keyword match validation        │
└──────────┬──────────┘     └──────────────────────────────────┘
           │
           ▼
┌─────────────────────┐
│   ats_checker.py    │
│   Validate Resume   │
│   Format + Keywords │
└─────────────────────┘
```

## Features

- **Multi-board scraping** — Scrapes 7 job boards via APIs with pagination, rate limiting, and deduplication
- **Multi-layer filtering** — Keyword, regex, location, language detection, company blacklist, and LLM-powered eligibility checks
- **Smart scoring** — Weighted scoring by tech match (35%), remote (25%), location (20%), title (20%)
- **LLM-powered resume tailoring** — GPT rewrites summary, reorders skills, and adapts bullet points to match each job posting (without fabricating experience)
- **ATS retry loop** — Validates keyword match %, retries with missing keywords up to 3 times
- **History tracking** — `seen_jobs.json` prevents duplicate processing across runs
- **Fully configurable** — All settings, profile, skills, and resume bullets in `config.yaml`
- **External prompts** — All GPT prompts in `prompts/` for easy editing without touching code

## Tech Stack

`Python` · `OpenAI API` · `BeautifulSoup` · `python-docx` · `YAML` · `REST APIs` · `Regex`

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/YOUR_USERNAME/job-hunter.git
cd job-hunter
pip install -r requirements.txt

# 2. Configure API key
cp .env.example .env
# Edit .env → add your OPENAI_API_KEY

# 3. Edit config.yaml with your profile, skills, and resume bullets

# 4. Run the full pipeline
python main.py
```

## Usage

```bash
# Full pipeline: scrape → filter → score → generate resumes
python main.py

# Use existing jobs file (skip scraping)
python main.py --jobs output/jobs_2026-03-15.json

# Scrape specific URLs only
python main.py --urls https://linkedin.com/jobs/view/123

# Skip seen jobs history
python main.py --no-history

# Run individual modules standalone
python job_finder.py                    # Scrape + filter + score only
python job_finder.py -o my_jobs.json    # Custom output
python ats_checker.py resume.docx       # Validate a resume
python job_scraper.py <url>             # Scrape a single job URL
```

## Output

```
output/
├── jobs_2026-03-15.json        # Scored jobs with metadata
├── report_2026-03-15.md        # Human-readable daily report
├── seen_jobs.json              # Dedup history
└── resumes/
    └── 2026-03-15/
        ├── CompanyA_JobTitle/
        │   ├── AG_Resume.docx  # Tailored resume
        │   ├── ats_report.txt  # ATS validation
        │   └── job_link.txt    # Job URL
        └── CompanyB_JobTitle/
            └── ...
```

## Configuration

All settings live in `config.yaml`:

```yaml
search:
  titles: ["full stack developer", "software engineer", ...]
  exclude_keywords: ["blockchain", "mobile developer", ...]
  exclude_companies: ["BairesDev", "Proxify", ...]
  blocked_countries: ["india", "philippines", ...]  # Low-salary geo-locks
  llm_filter: true                                   # Enable GPT filtering

llm:
  filter_model: "gpt-4o-mini"   # Model for job filtering
  tailor_model: "gpt-4o-mini"   # Model for resume tailoring

profile:
  years_experience: 5
  core_skills: ["javascript", "react", "python", ...]
  languages: ["English (C2)", "French (C2)"]

base_resume:
  bullets:
    company_name:
      - "Built X using Y, resulting in Z"
```

## Modules

| Module | Purpose |
|--------|---------|
| `main.py` | Pipeline orchestrator |
| `job_finder.py` | Multi-board scraping, filtering, scoring |
| `job_filter_llm.py` | GPT-based eligibility filter (language, location, role, seniority) |
| `resume_generator.py` | GPT resume tailoring with ATS retry loop |
| `ats_checker.py` | Resume ATS validation (fonts, format, keyword match) |
| `job_scraper.py` | Single URL scraper |
| `job_schema.py` | Job data structure utilities |
| `scrapers/` | Individual board scrapers (LinkedIn, RemoteOK, Himalayas, etc.) |
| `prompts/` | External GPT prompt templates |

## How the Filtering Pipeline Works

Jobs go through 6 filtering layers:

1. **Deduplication** — By URL, company+title signature, and `seen_jobs.json` history
2. **Keyword exclusion** — Titles containing "blockchain", "mobile developer", "data scientist", etc.
3. **Language detection** — Counts English/French word markers, rejects if neither language detected
4. **Location regex** — Pattern matching for "on-site only", "no visa sponsorship", "must be in office", etc.
5. **Blocked countries** — Rejects jobs geo-locked to low-salary markets
6. **LLM eligibility** — GPT-4o-mini checks language requirements, location feasibility, role type, and seniority fit

Each layer reduces noise while minimizing false negatives — when in doubt, the job passes through.

## How Resume Tailoring Works

1. Extracts top keywords from job description (frequency-based)
2. GPT rewrites professional summary starting with the exact job title
3. Reorders skills section to prioritize job-relevant technologies
4. Lightly rephrases bullet points to include job keywords (**never fabricates experience**)
5. Generates `.docx` from template
6. ATS checker validates keyword match %
7. If below threshold (45%), retries with emphasis on missing keywords (up to 3 attempts)

## License

[MIT](LICENSE)

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

## Roadmap

### Prompt Engineering
- [ ] **Filter prompt: reduce false negatives** — Loosen seniority check (currently rejects "Senior" roles that only need 3-4 years)
- [ ] **Filter prompt: better EOR detection** — Detect more Employer of Record providers beyond the current list (Deel, Oyster, Remote.com)
- [ ] **Filter prompt: salary-aware filtering** — Pass salary data to GPT and reject roles below minimum threshold
- [ ] **Tailor prompt: stronger keyword injection** — Improve first-pass keyword coverage to reduce ATS retry loops
- [ ] **Tailor prompt: role-specific templates** — Different tailoring strategies for frontend vs backend vs fullstack postings
- [ ] **Tailor prompt: cover letter generation** — Generate a tailored cover letter alongside the resume
- [ ] **Add prompt versioning** — Track prompt changes and their impact on filter/tailor quality

### Scrapers
- [ ] **AngelList / Wellfound** — Startup-focused remote jobs (API available)
- [ ] **Otta** — Curated tech roles with salary transparency
- [ ] **Glassdoor** — Large job board with salary data and company reviews
- [ ] **BuiltIn** — Tech company jobs across multiple cities
- [ ] **FlexJobs** — Vetted remote and flexible jobs
- [ ] **JustRemote** — Remote-only job board
- [ ] **Remote.co** — Curated remote positions
- [ ] **StackOverflow Jobs / Indeed API** — High-volume boards with developer focus
- [ ] **Hacker News (Who's Hiring)** — Monthly hiring threads with quality startup roles
- [ ] **Greenhouse / Lever / Workday** — Scrape company ATS pages directly for roles not posted on job boards
- [ ] **Y Combinator Work at a Startup** — YC-backed company listings

### Features
- [ ] **Email/Slack notifications** — "5 new jobs matched today"
- [ ] **Application tracking** — Track applied, interview, rejected, offer status per job
- [ ] **Web dashboard** — Simple Flask/Streamlit UI to browse jobs and manage applications
- [ ] **Scheduled runs** — Cron/Task Scheduler integration for daily automation
- [ ] **Multi-resume templates** — Different `.docx` templates for different role types

---

## License

[MIT](LICENSE)
