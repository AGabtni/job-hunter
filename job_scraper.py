#!/usr/bin/env python3
"""
Job Scraper Module
==================
Give it a job posting URL, get back a standardized job JSON.

Standalone:
    python job_scraper.py https://linkedin.com/jobs/view/12345
    python job_scraper.py https://remotive.com/some-job -o job.json

Pipeline:
    from job_scraper import scrape_job_url
    job = scrape_job_url("https://...")
"""

import sys
import re
import json
import logging
import argparse
import requests
from pathlib import Path
from urllib.parse import urlparse

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

from job_schema import create_job

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
}


def _fetch_page(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def _parse_linkedin(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title_el = soup.find("h1", class_="top-card-layout__title") or soup.find("h2", class_="top-card-layout__title")
    title = title_el.get_text(strip=True) if title_el else ""
    company_el = soup.find("a", class_="topcard__org-name-link") or soup.find("span", class_="topcard__flavor")
    company = company_el.get_text(strip=True) if company_el else ""
    loc_el = soup.find("span", class_="topcard__flavor--bullet")
    location = loc_el.get_text(strip=True) if loc_el else ""
    desc_div = soup.find("div", class_="show-more-less-html__markup") or soup.find("div", class_="description__text")
    description = desc_div.get_text(separator=" ", strip=True) if desc_div else ""
    return create_job(title=title, company=company, location=location, description=description[:5000], url=url, source="LinkedIn")


def _parse_remotive(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.find("h1") or soup.new_tag("span")).get_text(strip=True)
    company_el = soup.find("a", class_="company") or soup.find("span", class_="company")
    company = company_el.get_text(strip=True) if company_el else ""
    desc_el = soup.find("div", class_="job-description") or soup.find("div", id="job-description")
    description = desc_el.get_text(separator=" ", strip=True) if desc_el else ""
    return create_job(title=title, company=company, description=description[:5000], url=url, source="Remotive")


def _parse_remoteok(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title_el = soup.find("h2", itemprop="title") or soup.find("h1")
    title = title_el.get_text(strip=True) if title_el else ""
    company_el = soup.find("h3", itemprop="name")
    company = company_el.get_text(strip=True) if company_el else ""
    desc_el = soup.find("div", class_="description") or soup.find("div", itemprop="description")
    description = desc_el.get_text(separator=" ", strip=True) if desc_el else ""
    tags = [t.get_text(strip=True) for t in soup.find_all("a", class_="tag")]
    return create_job(title=title, company=company, description=description[:5000], url=url, source="RemoteOK", tags=tags)


def _parse_weworkremotely(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title_el = soup.find("h1")
    title = title_el.get_text(strip=True) if title_el else ""
    company_el = soup.find("h2") or soup.find("a", class_="company")
    company = company_el.get_text(strip=True) if company_el else ""
    desc_el = soup.find("div", class_="listing-container") or soup.find("div", id="job-listing-show-container")
    description = desc_el.get_text(separator=" ", strip=True) if desc_el else ""
    return create_job(title=title, company=company, description=description[:5000], url=url, source="WeWorkRemotely")


def _parse_arbeitnow(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title_el = soup.find("h1")
    title = title_el.get_text(strip=True) if title_el else ""
    company_el = soup.find("a", class_="company-name")
    company = company_el.get_text(strip=True) if company_el else ""
    desc_el = soup.find("div", class_="job-description")
    description = desc_el.get_text(separator=" ", strip=True) if desc_el else ""
    return create_job(title=title, company=company, description=description[:5000], url=url, source="Arbeitnow")


def _parse_generic(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    for sel in ["h1", "h2.job-title", ".job-title", "[itemprop='title']"]:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            title = el.get_text(strip=True)
            break
    company = ""
    for sel in [".company", ".company-name", "[itemprop='hiringOrganization']", "[itemprop='name']"]:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            company = el.get_text(strip=True)
            break
    description = ""
    for sel in [".job-description", ".description", "#job-description", "[itemprop='description']", "article", ".content"]:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(separator=" ", strip=True)
            if len(text) > 100:
                description = text
                break
    if not description:
        blocks = [tag.get_text(separator=" ", strip=True) for tag in soup.find_all(["div", "section", "article"]) if 200 < len(tag.get_text(strip=True)) < 10000]
        if blocks:
            description = max(blocks, key=len)
    if not title:
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            title = og["content"]
    return create_job(title=title, company=company, description=description[:5000], url=url, source=urlparse(url).netloc)


PARSERS = {
    "linkedin.com": _parse_linkedin,
    "remotive.com": _parse_remotive,
    "remoteok.com": _parse_remoteok,
    "remoteok.io": _parse_remoteok,
    "weworkremotely.com": _parse_weworkremotely,
    "arbeitnow.com": _parse_arbeitnow,
}


def scrape_job_url(url: str) -> dict:
    """Scrape a job posting URL and return standardized job dict."""
    if not HAS_BS4:
        logger.error("beautifulsoup4 not installed")
        return create_job(url=url)
    try:
        html = _fetch_page(url)
    except Exception as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return create_job(url=url)

    domain = urlparse(url).netloc.lower().replace("www.", "")
    parser = next((p for d, p in PARSERS.items() if d in domain), _parse_generic)
    job = parser(html, url)

    if not job["title"] and not job["description"]:
        logger.warning(f"Could not extract data from {url}")
    return job


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser(description="Scrape a job posting URL into standardized JSON")
    parser.add_argument("url", help="Job posting URL")
    parser.add_argument("-o", "--output", help="Output JSON file (default: stdout)")
    args = parser.parse_args()
    job = scrape_job_url(args.url)
    output = json.dumps(job, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        logger.info(f"Saved: {args.output} | Title: {job['title']} | Desc: {len(job['description'])} chars")
    else:
        print(output)


if __name__ == "__main__":
    main()