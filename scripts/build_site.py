#!/usr/bin/env python3
"""
Build static site into _site directory using Python and Jinja2.
Renders index.html, calendar.html, and conference.html with _data/conferences.yml,
_data/types.yml, and _config.yml from the exact paperswithcode layout.
"""
import os
import re
import shutil
import json
from datetime import datetime, timezone
from pathlib import Path
import yaml
import jinja2

REPO_ROOT = Path(__file__).resolve().parent.parent

def load_yaml(path):
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # Clean YAML anchors
    content = re.sub(r'&\w+', '', content)
    content = re.sub(r'\*\w+', '', content)
    try:
        return yaml.safe_load(content) or []
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return []

def preprocess_liquid_to_jinja(content):
    content = content.replace("\r\n", "\n")
    # Preprocess {% include head.html %} -> {% include 'head.html' %}
    content = re.sub(r"\{\%\s*include\s+([a-zA-Z0-9_\-\.]+)\s*\%\}", r"{% include '\1' %}", content)
    # Preprocess prepend:site.baseurl filter
    content = re.sub(r"\{\{\s*\"([^\"]+)\"\s*\|\s*prepend:\s*site\.baseurl\s*\}\}", r"{{ site.baseurl }}\1", content)
    content = re.sub(r"\{\{\s*site\.baseurl\s*\|\s*prepend:\s*site\.baseurl\s*\}\}", r"{{ site.baseurl }}", content)
    # Preprocess date filter
    content = re.sub(r"\{\{\s*site\.time\s*\|\s*date:\s*'%s'\s*\}\}", r"{{ site.time_epoch }}", content)
    # Preprocess slice: -2, 3 filter -> slice_filter('-2,3')
    content = re.sub(r"\{\{\s*conf\.year\s*\|\s*slice:\s*(-?\d+)\s*,\s*(\d+)\s*\}\}", r"{{ conf.year | slice_filter('\1,\2') }}", content)
    return content

def slice_filter(value, start_len):
    if not value:
        return ""
    try:
        parts = [int(p.strip()) for p in start_len.split(',')]
        if len(parts) == 1:
            return str(value)[parts[0]:]
        elif len(parts) == 2:
            start, length = parts
            if start < 0:
                return str(value)[start:]
            return str(value)[start:start+length]
    except Exception:
        pass
    return str(value)

def main():
    config = load_yaml(REPO_ROOT / "_config.yml") or {}
    conferences = load_yaml(REPO_ROOT / "_data" / "conferences.yml") or []
    types_data = load_yaml(REPO_ROOT / "_data" / "types.yml") or []

    # Ensure list types for sub tags
    for conf in conferences:
        if isinstance(conf.get("sub"), str):
            conf["sub"] = [conf["sub"]]
        elif not conf.get("sub"):
            conf["sub"] = ["SE"]

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Config setup
    config["baseurl"] = ""
    config["time"] = datetime.now(timezone.utc)
    config["time_epoch"] = str(int(datetime.now(timezone.utc).timestamp()))
    config["today"] = today_str
    config["data"] = {
        "conferences": conferences,
        "types": types_data
    }
    
    # Safe defaults for nested properties
    if "twitter" not in config:
        config["twitter"] = {"hashtag": config.get("twitter_hashtag", "modeling")}
    if "domain" not in config or not config["domain"]:
        config["domain"] = "modeling-deadlines"

    # Setup Jinja2 Environment with loaders
    loader = jinja2.ChoiceLoader([
        jinja2.FileSystemLoader(str(REPO_ROOT / "_includes")),
        jinja2.FileSystemLoader(str(REPO_ROOT)),
        jinja2.FileSystemLoader(str(REPO_ROOT / "_pages"))
    ])

    env = jinja2.Environment(loader=loader, autoescape=False)

    # Custom filters
    env.filters["jsonify"] = lambda v: json.dumps(v)
    env.filters["escape"] = lambda x: str(x).replace('"', '&quot;').replace("'", "&#39;") if x else ""
    env.filters["slice_filter"] = slice_filter

    out_dir = REPO_ROOT / "_site"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Compile index.html
    raw_index = (REPO_ROOT / "index.html").read_text(encoding="utf-8")
    raw_index = raw_index.replace("\r\n", "\n")
    raw_index = re.sub(r"^---\n.*?\n---\n", "", raw_index, flags=re.DOTALL)
    jinja_index = preprocess_liquid_to_jinja(raw_index)
    rendered_index = env.from_string(jinja_index).render(site=config)
    (out_dir / "index.html").write_text(rendered_index, encoding="utf-8")
    print("[Build] Generated index.html")

    # 2. Compile calendar.html
    raw_calendar = (REPO_ROOT / "calendar.html").read_text(encoding="utf-8")
    raw_calendar = raw_calendar.replace("\r\n", "\n")
    raw_calendar = re.sub(r"^---\n.*?\n---\n", "", raw_calendar, flags=re.DOTALL)
    jinja_calendar = preprocess_liquid_to_jinja(raw_calendar)
    rendered_calendar = env.from_string(jinja_calendar).render(site=config)
    (out_dir / "calendar").mkdir(parents=True, exist_ok=True)
    (out_dir / "calendar" / "index.html").write_text(rendered_calendar, encoding="utf-8")
    print("[Build] Generated calendar/index.html")

    # 3. Compile conference.html
    raw_conf = (REPO_ROOT / "_pages" / "conference.html").read_text(encoding="utf-8")
    raw_conf = raw_conf.replace("\r\n", "\n")
    raw_conf = re.sub(r"^---\n.*?\n---\n", "", raw_conf, flags=re.DOTALL)
    jinja_conf = preprocess_liquid_to_jinja(raw_conf)
    rendered_conf = env.from_string(jinja_conf).render(site=config)
    (out_dir / "conference").mkdir(parents=True, exist_ok=True)
    (out_dir / "conference" / "index.html").write_text(rendered_conf, encoding="utf-8")
    print("[Build] Generated conference/index.html")

    # Copy static assets to _site/static
    static_src = REPO_ROOT / "static"
    static_dst = out_dir / "static"
    if static_src.exists():
        if static_dst.exists():
            shutil.rmtree(static_dst)
        shutil.copytree(static_src, static_dst)
        print(f"[Build] Copied static directory to {static_dst}")

    # Copy ics file if present
    ics_src = REPO_ROOT / "conf-deadlines.ics"
    if ics_src.exists():
        shutil.copy(ics_src, out_dir / "conf-deadlines.ics")

if __name__ == "__main__":
    main()
