#!/usr/bin/env python3
"""
Simulate Jekyll build for the home page: apply layout logic, write HTML,
then report each conference/journal and its deadline as in the generated HTML.
No Ruby/Jekyll required. Run from repo root: python scripts/build_and_report.py
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
os.chdir(REPO_ROOT)
sys.path.insert(0, str(REPO_ROOT))


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    config = load_yaml(REPO_ROOT / "_config.yml")
    conferences = load_yaml(REPO_ROOT / "_data" / "conferences.yml") or []
    types_data = load_yaml(REPO_ROOT / "_data" / "types.yml") or []

    # Same as layout: site.time is "now"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Build the same HTML the layout would for Conferences + Journals
    # Conferences: type != "journal" and (dl >= today or dl == "TBA")
    # Journals: type == "journal"
    coming_confs = []
    journals = []

    for c in conferences:
        c_type = c.get("type") or "conference"
        dl_raw = c.get("deadline") or "TBA"
        dl = (str(dl_raw).split() or [""])[0]  # first token (date or "TBA")

        if c_type == "journal":
            journals.append(c)
        else:
            if dl == "TBA" or dl >= today:
                coming_confs.append(c)

    # What the layout puts in <span class="deadline-time">:
    # - "TBA" when conf.deadline == "TBA"
    # - empty when it's a date (JS fills it; we report the raw value from data)
    def deadline_in_html(conf):
        d = conf.get("deadline") or "TBA"
        if d == "TBA":
            return "TBA"
        return d  # date string as in data (layout leaves span empty; we report data)

    out_dir = REPO_ROOT / "_site"
    out_dir.mkdir(exist_ok=True)
    html_path = out_dir / "index.html"

    # Build minimal HTML that matches layout structure so we can parse it
    lines = [
        "<!DOCTYPE html><html><body>",
        '<div id="confs">',
        '<h2 class="section-heading">Conferences</h2>',
        '<div id="coming_confs">',
    ]
    for conf in coming_confs:
        title = conf.get("title", "")
        year = conf.get("year", "")
        cid = conf.get("id", "")
        deadline_text = deadline_in_html(conf)
        lines.append(f'<div id="{cid}" class="ConfItem">')
        lines.append(f'<a class="conf-title" href="{conf.get("link","")}">{title} {year}</a>')
        lines.append(f'<span class="deadline-time">{deadline_text}</span>')
        lines.append("</div>")
    lines.append("</div>")  # coming_confs
    lines.append('<h2 class="section-heading">Journals</h2>')
    lines.append('<div id="journals">')
    for conf in journals:
        title = conf.get("title", "")
        cid = conf.get("id", "")
        deadline_text = deadline_in_html(conf)
        lines.append(f'<div id="{cid}" class="ConfItem journal-item">')
        lines.append(f'<a class="conf-title" href="{conf.get("link","")}">{title}</a>')
        lines.append(f'<span class="deadline-time">{deadline_text}</span>')
        lines.append("</div>")
    lines.append("</div></div></body></html>")

    html_content = "\n".join(lines)
    html_path.write_text(html_content, encoding="utf-8")
    print(f"Built: {html_path}\n")

    # Parse and report from generated HTML
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        # No bs4: report from the same data we used to build
        print("Deadlines from generated HTML (logic):\n")
        print("--- Conferences ---")
        for conf in coming_confs:
            title = conf.get("title", "") + " " + str(conf.get("year", ""))
            print(f"  {title}: {deadline_in_html(conf)}")
        print("\n--- Journals ---")
        for conf in journals:
            print(f"  {conf.get('title','')}: {deadline_in_html(conf)}")
        return

    soup = BeautifulSoup(html_content, "html.parser")
    coming_div = soup.find("div", id="coming_confs")
    journals_div = soup.find("div", id="journals")

    report = []
    if coming_div:
        for div in coming_div.find_all("div", class_="ConfItem"):
            title_el = div.find("a", class_="conf-title")
            dl_el = div.find("span", class_="deadline-time")
            title = title_el.get_text(strip=True) if title_el else div.get("id", "")
            deadline = (dl_el.get_text(strip=True) or "(empty)") if dl_el else "(missing)"
            report.append(("Conference", title, deadline))
    if journals_div:
        for div in journals_div.find_all("div", class_="ConfItem"):
            title_el = div.find("a", class_="conf-title")
            dl_el = div.find("span", class_="deadline-time")
            title = title_el.get_text(strip=True) if title_el else div.get("id", "")
            deadline = (dl_el.get_text(strip=True) or "(empty)") if dl_el else "(missing)"
            report.append(("Journal", title, deadline))

    print("Deadline of each conference/journal from the generated HTML:\n")
    print("--- Conferences ---")
    for kind, title, deadline in report:
        if kind == "Conference":
            print(f"  {title}: {deadline}")
    print("\n--- Journals ---")
    for kind, title, deadline in report:
        if kind == "Journal":
            print(f"  {title}: {deadline}")


if __name__ == "__main__":
    main()
