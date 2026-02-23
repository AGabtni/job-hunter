"""Generate tailored .docx resumes for top job matches."""

import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from docx import Document
    from docx.shared import Pt, Inches, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False
    logger.warning("python-docx not installed. Run: pip install python-docx")


def sanitize_filename(name: str) -> str:
    """Make a string safe for filenames."""
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', '_', name.strip())
    return name[:80]


def generate_resume_docx(job: dict, tailored_data: dict, config: dict, output_dir: Path) -> Path | None:
    """Generate a tailored .docx resume for a specific job."""
    if not HAS_DOCX:
        return None
    
    profile = config["profile"]
    base_resume = config["base_resume"]
    
    company = job.get("company", "Unknown")
    title = job.get("title", "Unknown")
    
    doc = Document()
    
    # --- Styles ---
    style = doc.styles["Normal"]
    font = style.font
    font.name = "Calibri"
    font.size = Pt(10.5)
    font.color.rgb = RGBColor(0, 0, 0)
    
    # --- Header: Name ---
    name_para = doc.add_paragraph()
    name_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    name_run = name_para.add_run(profile["name"].upper())
    name_run.bold = True
    name_run.font.size = Pt(18)
    name_run.font.name = "Calibri"
    name_para.space_after = Pt(2)
    
    # --- Header: Title ---
    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_para.add_run("Full-Stack Developer")
    title_run.font.size = Pt(12)
    title_run.font.color.rgb = RGBColor(50, 50, 50)
    title_run.font.name = "Calibri"
    title_para.space_after = Pt(2)
    
    # --- Header: Contact ---
    contact_para = doc.add_paragraph()
    contact_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    contact_run = contact_para.add_run(
        f"{profile['email']}  |  LinkedIn  |  French (C2) & English (C2)"
    )
    contact_run.font.size = Pt(9)
    contact_run.font.color.rgb = RGBColor(80, 80, 80)
    contact_run.font.name = "Calibri"
    contact_para.space_after = Pt(6)
    
    # --- Summary ---
    add_section_header(doc, "PROFESSIONAL SUMMARY")
    summary_text = tailored_data.get("summary", "")
    if not summary_text:
        summary_text = (
            f"Full-Stack Developer with {profile['years_experience']}+ years of experience "
            "building scalable web applications, REST APIs, and cloud-based solutions. "
            "Bilingual (French C2 / English C2) with expertise in JavaScript/TypeScript, "
            "React, Node.js, Python, and modern DevOps practices."
        )
    summary_para = doc.add_paragraph(summary_text)
    summary_para.style.font.size = Pt(10.5)
    summary_para.space_after = Pt(6)
    
    # --- Skills ---
    add_section_header(doc, "TECHNICAL SKILLS")
    
    highlighted = tailored_data.get("skills_to_highlight", [])
    
    skills_data = [
        ("Languages", "JavaScript, TypeScript, Python, Java, C++, SQL, PHP"),
        ("Frontend", "React.js, HTML/CSS, Tailwind, Bootstrap, Responsive Design"),
        ("Backend", "Node.js, Express, Spring Boot, REST APIs, .NET"),
        ("Databases", "PostgreSQL, MongoDB, SQL Server"),
        ("Cloud & DevOps", "Azure, Docker, CI/CD, Git, SAP Cloud Platform"),
        ("Tools", "GitHub Copilot, AI-assisted development, Agile/Scrum"),
    ]
    
    for label, skills in skills_data:
        p = doc.add_paragraph()
        p.space_after = Pt(1)
        p.space_before = Pt(1)
        label_run = p.add_run(f"{label}: ")
        label_run.bold = True
        label_run.font.size = Pt(10)
        label_run.font.name = "Calibri"
        skills_run = p.add_run(skills)
        skills_run.font.size = Pt(10)
        skills_run.font.name = "Calibri"
    
    # --- Experience ---
    add_section_header(doc, "PROFESSIONAL EXPERIENCE")
    
    roles = [
        {
            "title": "Full-Stack Developer",
            "company": "City of Gatineau",
            "dates": "Sept 2023 – Present",
            "key": "city_of_gatineau",
        },
        {
            "title": "Software Engineer",
            "company": "Precision OS",
            "dates": "Jan 2022 – Sept 2023",
            "key": "precision_os",
        },
        {
            "title": "Full-Stack Developer",
            "company": "Syntax (Consulting)",
            "dates": "Jan 2021 – Jan 2022",
            "key": "syntax",
        },
        {
            "title": "Web Developer",
            "company": "University of Ottawa",
            "dates": "May 2019 – Jan 2021",
            "key": "uottawa",
        },
    ]
    
    tailored_bullets = tailored_data.get("bullets", {})
    
    for role in roles:
        # Role header
        role_para = doc.add_paragraph()
        role_para.space_before = Pt(8)
        role_para.space_after = Pt(2)
        
        title_run = role_para.add_run(f"{role['title']} | {role['company']}")
        title_run.bold = True
        title_run.font.size = Pt(10.5)
        title_run.font.name = "Calibri"
        
        role_para.add_run("    ")
        
        date_run = role_para.add_run(role["dates"])
        date_run.font.size = Pt(10)
        date_run.font.color.rgb = RGBColor(80, 80, 80)
        date_run.font.name = "Calibri"
        
        # Bullets - use tailored if available, else base
        bullets = tailored_bullets.get(role["key"], base_resume["bullets"].get(role["key"], []))
        
        for bullet_text in bullets:
            bp = doc.add_paragraph(style="List Bullet")
            bp.space_before = Pt(1)
            bp.space_after = Pt(1)
            br = bp.add_run(bullet_text)
            br.font.size = Pt(10)
            br.font.name = "Calibri"
    
    # --- Education ---
    add_section_header(doc, "EDUCATION")
    
    edu_para = doc.add_paragraph()
    edu_para.space_before = Pt(4)
    edu_title = edu_para.add_run("Bachelor of Applied Science, Computer Engineering")
    edu_title.bold = True
    edu_title.font.size = Pt(10.5)
    edu_title.font.name = "Calibri"
    edu_para.add_run("    ")
    edu_date = edu_para.add_run("2016 – 2020")
    edu_date.font.size = Pt(10)
    edu_date.font.color.rgb = RGBColor(80, 80, 80)
    edu_date.font.name = "Calibri"
    
    uni_para = doc.add_paragraph("University of Ottawa")
    uni_para.space_before = Pt(0)
    uni_run = uni_para.runs[0]
    uni_run.font.size = Pt(10)
    uni_run.font.color.rgb = RGBColor(80, 80, 80)
    uni_run.font.name = "Calibri"
    
    # --- Save ---
    safe_company = sanitize_filename(company)
    safe_title = sanitize_filename(title)
    filename = f"Resume_{safe_company}_{safe_title}.docx"
    filepath = output_dir / filename
    
    doc.save(str(filepath))
    logger.info(f"Generated resume: {filename}")
    
    return filepath


def add_section_header(doc, text: str):
    """Add a section header with bottom border."""
    para = doc.add_paragraph()
    para.space_before = Pt(12)
    para.space_after = Pt(4)
    run = para.add_run(text)
    run.bold = True
    run.font.size = Pt(11)
    run.font.name = "Calibri"
    run.font.color.rgb = RGBColor(0, 0, 0)
    
    # Add bottom border
    from docx.oxml.ns import qn
    pPr = para._p.get_or_add_pPr()
    pBdr = pPr.makeelement(qn('w:pBdr'), {})
    bottom = pBdr.makeelement(qn('w:bottom'), {
        qn('w:val'): 'single',
        qn('w:sz'): '6',
        qn('w:space'): '1',
        qn('w:color'): '000000',
    })
    pBdr.append(bottom)
    pPr.append(pBdr)


def generate_all_resumes(scored_jobs: list[dict], tailored: dict, config: dict, output_dir: Path) -> list[Path]:
    """Generate tailored .docx resumes for all tailored jobs."""
    if not HAS_DOCX:
        logger.error("python-docx not installed. Cannot generate resumes.")
        return []
    
    resumes_dir = output_dir / "resumes"
    resumes_dir.mkdir(exist_ok=True)
    
    generated = []
    
    for job in scored_jobs:
        job_url = job.get("url", "")
        if job_url not in tailored:
            continue
        
        filepath = generate_resume_docx(job, tailored[job_url], config, resumes_dir)
        if filepath:
            generated.append(filepath)
    
    logger.info(f"Generated {len(generated)} tailored resumes in {resumes_dir}")
    return generated
