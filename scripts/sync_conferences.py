#!/usr/bin/env python3
"""
Sync _data/conferences.yml from upstream (already merged by workflow) with
Researchr API and optionally WikiCFP RSS. Idempotent; only adds/updates.
"""
from __future__ import annotations

import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests
import yaml

# Path to data file (repo root = cwd when run from workflow)
DATA_DIR = Path(__file__).resolve().parent.parent
CONF_FILE = DATA_DIR / "_data" / "conferences.yml"

# Researchr API base
RESEARCHR_API = "https://researchr.org/api/search/conference"

# Conference series to query (search terms). Order doesn't matter; we merge by link.
RESEARCHR_SERIES = [
    "models", "icse", "ase", "er", "ecmfa", "sle", "fse", "re", "splash",
    "ssbse", "poem", "fase", "modelsward", "annsim", "edtconf", "modellierung",
]

# Optional: WikiCFP RSS (one feed). Set to None to disable.
WIKICFP_RSS = "http://www.wikicfp.com/cfp/rss?cat=software"

# Default timezone and sub; acronym -> sub mapping for known venues
DEFAULT_TIMEZONE = "AoE (UTC-12h)"
DEFAULT_SUB = "SE"
ACRONYM_SUB = {
    "ER": "DB", "SPLASH": "PL",
}

# Consider submission deadlines from this year through two years ahead
CURRENT_YEAR = datetime.utcnow().year
YEAR_MIN = CURRENT_YEAR
YEAR_MAX = CURRENT_YEAR + 2

# Canonical list: every conference and journal that must appear on the page.
# If the API doesn't return them, these are added with TBA so they still show.
# Links are the authoritative URLs you requested.
CANONICAL_CONFERENCES = [
    {"title": "MODELS", "id": "models2026", "link": "https://conf.researchr.org/home/models-2026", "year": 2026, "sub": "SE"},
    {"title": "MODELS Workshops", "id": "models-workshops2026", "link": "https://conf.researchr.org/track/models-2026/models-2026-workshops", "year": 2026, "sub": "SE"},
    {"title": "ECMFA", "id": "ecmfa2026", "link": "https://www.ecmfa.org/", "year": 2026, "sub": "SE"},
    {"title": "SLE", "id": "sle2026", "link": "https://conf.researchr.org/home/sle-2026", "year": 2026, "sub": "SE"},
    {"title": "ER", "id": "er2026", "link": "https://er2026.org", "year": 2026, "sub": "DB"},
    {"title": "POEM", "id": "poem2026", "link": "https://poem-conference.org", "year": 2026, "sub": "SE"},
    {"title": "ICSE", "id": "icse2026", "link": "https://conf.researchr.org/home/icse-2026", "year": 2026, "sub": "SE"},
    {"title": "ASE", "id": "ase2026", "link": "https://conf.researchr.org/home/ase-2026", "year": 2026, "sub": "SE"},
    {"title": "SSBSE", "id": "ssbse2026", "link": "https://conf.researchr.org/home/ssbse-2026", "year": 2026, "sub": "SE"},
    {"title": "ANNSIM", "id": "annsim2026", "link": "https://scs.org/annsim/", "year": 2026, "sub": "SE"},
    {"title": "MoDELSWARD", "id": "modelsward2026", "link": "https://modelsward.scitevents.org", "year": 2026, "sub": "SE"},
    {"title": "FASE", "id": "fase2026", "link": "https://etaps.org/events/fase", "year": 2026, "sub": "SE"},
]
CANONICAL_JOURNALS = [
    {"title": "Software and Systems Modeling (SoSyM)", "id": "sosym", "link": "https://www.springer.com/journal/10270", "year": 2026, "sub": "SE"},
    {"title": "Journal of Systems and Software", "id": "jss", "link": "https://www.sciencedirect.com/journal/journal-of-systems-and-software", "year": 2026, "sub": "SE"},
    {"title": "Empirical Software Engineering", "id": "emse", "link": "https://www.springer.com/journal/10664", "year": 2026, "sub": "SE"},
    {"title": "ACM TOSEM", "id": "tosem", "link": "https://dl.acm.org/journal/tosem", "year": 2026, "sub": "SE"},
    {"title": "IEEE TSE", "id": "tse", "link": "https://www.computer.org/csdl/journal/ts", "year": 2026, "sub": "SE"},
    {"title": "Journal of Object Technology", "id": "jot", "link": "https://www.jot.fm", "year": 2026, "sub": "SE"},
    {"title": "Simulation Modelling Practice and Theory", "id": "smpat", "link": "https://www.sciencedirect.com/journal/simulation-modelling-practice-and-theory", "year": 2026, "sub": "SE"},
]


def normalize_key(key: str) -> str:
    """Researchr key (e.g. models:2025, ase-2025) -> conf.researchr.org slug."""
    if not key:
        return ""
    return key.replace(":", "-").strip()


def researchr_link(key: str) -> str:
    """Build conf.researchr.org home URL from API key."""
    slug = normalize_key(key)
    if not slug:
        return ""
    return f"https://conf.researchr.org/home/{slug}"


def format_date_range(start: str | None, end: str | None) -> str:
    """Turn YYYY-MM-DD start/end into human date like 'October 5-10, 2025'."""
    if not start or start == "null":
        return ""
    try:
        d1 = datetime.strptime(start[:10], "%Y-%m-%d")
    except ValueError:
        return start
    if not end or end == "null" or end[:10] == start[:10]:
        return f"{d1.strftime('%B')} {d1.day}, {d1.year}"
    try:
        d2 = datetime.strptime(end[:10], "%Y-%m-%d")
    except ValueError:
        return f"{d1.strftime('%B')} {d1.day}, {d1.year}"
    if d1.month == d2.month and d1.year == d2.year:
        return f"{d1.strftime('%B')} {d1.day}-{d2.day}, {d1.year}"
    return f"{d1.strftime('%B')} {d1.day} - {d2.strftime('%B')} {d2.day}, {d2.year}"


def extract_year(s: str | None) -> int | None:
    """First 4 digits from a date string."""
    if not s or s == "null":
        return None
    m = re.match(r"(\d{4})", s)
    return int(m.group(1)) if m else None


def fetch_researchr(term: str) -> list[dict]:
    """One API call for a search term; returns list of conference objects."""
    url = f"{RESEARCHR_API}/{term.replace(' ', '+')}"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("result") or []
    except Exception:
        return []


def researchr_to_entry(c: dict) -> dict | None:
    """Map one Researchr conference object to our YAML entry, or None if skip."""
    submission = c.get("submission")
    if not submission or submission == "null":
        return None
    year = extract_year(submission)
    if year is None or year < YEAR_MIN or year > YEAR_MAX:
        return None
    key = c.get("key") or ""
    link = researchr_link(key)
    if not link:
        return None
    acronym = (c.get("acronym") or "").strip()
    title = acronym or (c.get("fullname") or "").strip() or "Conference"
    start = c.get("startDate")
    end = c.get("endDate")
    city = (c.get("city") or "").strip()
    country = (c.get("country") or "").strip()
    place = ", ".join(filter(None, [city, country])) or "TBA"
    sub = ACRONYM_SUB.get(acronym.upper(), DEFAULT_SUB)
    # id: lowercase acronym + year; ensure unique by using key if needed
    base_id = re.sub(r"[^a-z0-9]", "", acronym.lower()) if acronym else key.replace(":", "").replace("-", "")
    if not base_id:
        base_id = "conf"
    entry_id = f"{base_id}{year}"
    return {
        "title": title,
        "hindex": None,
        "year": year,
        "id": entry_id,
        "link": link,
        "deadline": f"{submission[:10]} 23:59:59",
        "timezone": DEFAULT_TIMEZONE,
        "date": format_date_range(start, end),
        "place": place,
        "sub": [sub],
        "type": "conference",
    }


def _normalize_yaml_list(content: str) -> str:
    """Fix upstream YAML where some list items have '  - ' instead of '- ' (parser error)."""
    return re.sub(r"\n  - ", r"\n- ", content)


def load_existing() -> list[dict]:
    """Load existing _data/conferences.yml; return list of entries."""
    if not CONF_FILE.exists():
        return []
    with open(CONF_FILE, encoding="utf-8") as f:
        raw = f.read()
    raw = _normalize_yaml_list(raw)
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError:
        return []
    if data is None:
        return []
    entries = data if isinstance(data, list) else []
    for e in entries:
        if isinstance(e.get("sub"), str):
            e["sub"] = [e["sub"]]
    return entries


def save_entries(entries: list[dict]) -> None:
    """Write list of entries to _data/conferences.yml."""
    CONF_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONF_FILE, "w", encoding="utf-8") as f:
        f.write("---\n\n")
        yaml.dump(
            entries,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=1000,
        )


def merge_researchr(existing: list[dict], api_entries: list[dict]) -> list[dict]:
    """Merge API entries into existing. Match by link; update first match or append. Preserve note/timezone."""
    existing_links = [e.get("link") for e in existing]
    used_api_links = set()
    result = []
    for e in list(existing):
        link = e.get("link")
        match = next(
            (a for a in api_entries if a.get("link") == link and a["link"] not in used_api_links),
            None,
        )
        if match:
            used_api_links.add(link)
            e["deadline"] = match.get("deadline", e["deadline"])
            e["date"] = match.get("date") or e.get("date")
            e["place"] = match.get("place") or e.get("place")
            e["year"] = match.get("year", e.get("year"))
        result.append(e)
    for api_e in api_entries:
        link = api_e.get("link")
        if link and link not in existing_links:
            result.append(api_e)
            existing_links.append(link)
    return result


def fetch_wikicfp() -> list[dict]:
    """Fetch WikiCFP RSS and return minimal YAML-shaped entries (optional)."""
    if not WIKICFP_RSS:
        return []
    try:
        req = urllib.request.Request(WIKICFP_RSS, headers={"User-Agent": "ConferenceSync/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            tree = ET.parse(resp)
    except Exception:
        return []
    root = tree.getroot()
    # Handle both RSS 2.0 and namespace
    channel = root.find("channel") or root.find("{http://purl.org/rss/1.0/}channel") or root
    items = channel.findall("item") or channel.findall("{http://purl.org/rss/1.0/}item") or []
    out = []
    for item in items[:50]:
        title_el = item.find("title") or item.find("{http://purl.org/rss/1.0/}title")
        link_el = item.find("link") or item.find("{http://purl.org/rss/1.0/}link")
        title = (title_el.text or "").strip() if title_el is not None else ""
        link = (link_el.text or "").strip() if link_el is not None else ""
        if not title or not link:
            continue
        desc_el = item.find("description") or item.find("{http://purl.org/rss/1.0/}description")
        desc = (desc_el.text or "") if desc_el is not None else ""
        # Try to extract deadline from description (e.g. "Deadline: 2025-03-01")
        deadline_str = None
        for m in re.finditer(r"(?:deadline|due|submission).*?(\d{4})-(\d{2})-(\d{2})", desc, re.I):
            deadline_str = f"{m.group(1)}-{m.group(2)}-{m.group(3)} 23:59:59"
            break
        if not deadline_str:
            continue
        year = extract_year(deadline_str)
        if year is None or year < YEAR_MIN or year > YEAR_MAX:
            continue
        entry_id = re.sub(r"[^a-z0-9]", "", title.lower())[:20] + str(year)
        out.append({
            "title": title[:80],
            "hindex": None,
            "year": year,
            "id": entry_id,
            "link": link,
            "deadline": deadline_str,
            "timezone": DEFAULT_TIMEZONE,
            "date": "",
            "place": "",
            "sub": [DEFAULT_SUB],
            "type": "conference",
        })
    return out


def merge_wikicfp(existing: list[dict], rss_entries: list[dict]) -> list[dict]:
    """Add RSS entries that are not already in existing (by link)."""
    existing_links = {e.get("link") for e in existing if e.get("link")}
    for e in rss_entries:
        if e.get("link") and e["link"] not in existing_links:
            existing.append(e)
            existing_links.add(e["link"])
    return existing


def sort_entries(entries: list[dict]) -> list[dict]:
    """Sort by deadline descending (upcoming first), then by year, then title."""
    def key(e):
        d = e.get("deadline") or ""
        y = e.get("year") or 0
        t = e.get("title") or ""
        return (d, y, t)
    return sorted(entries, key=key, reverse=True)


def canonical_entry(c: dict, *, is_journal: bool = False) -> dict:
    """Turn a canonical dict into a full YAML entry (deadline TBA if not set)."""
    x = c.get("sub", DEFAULT_SUB)
    sub_list = [x] if isinstance(x, str) else list(x) if x else [DEFAULT_SUB]
    e = {
        "title": c["title"],
        "hindex": None,
        "year": c["year"],
        "id": c["id"],
        "link": c["link"],
        "deadline": c.get("deadline", "TBA"),
        "timezone": DEFAULT_TIMEZONE,
        "date": c.get("date", ""),
        "place": c.get("place", ""),
        "sub": sub_list,
        "type": "journal" if is_journal else "conference",
    }
    if is_journal:
        e["note"] = "Rolling submission"
    if c.get("note"):
        e["note"] = c["note"]
    return e


def ensure_canonical(merged: list[dict]) -> list[dict]:
    """Ensure every canonical conference and journal appears. Add with TBA if missing."""
    by_link = {e.get("link"): e for e in merged}
    out = list(merged)
    for c in CANONICAL_CONFERENCES:
        link = c["link"]
        if link not in by_link:
            entry = canonical_entry(c)
            out.append(entry)
            by_link[link] = entry
    for c in CANONICAL_JOURNALS:
        link = c["link"]
        if link not in by_link:
            entry = canonical_entry(c, is_journal=True)
            out.append(entry)
            by_link[link] = entry
    journal_links = {c["link"] for c in CANONICAL_JOURNALS}
    for e in out:
        if e.get("link") in journal_links:
            e["type"] = "journal"
    return out


def main() -> None:
    existing = load_existing()
    api_entries = []
    for term in RESEARCHR_SERIES:
        for c in fetch_researchr(term):
            e = researchr_to_entry(c)
            if e:
                api_entries.append(e)
    # Dedupe API by link (keep first)
    seen = set()
    unique_api = []
    for e in api_entries:
        if e["link"] not in seen:
            seen.add(e["link"])
            unique_api.append(e)
    merged = merge_researchr(existing, unique_api)
    rss_entries = fetch_wikicfp()
    merged = merge_wikicfp(merged, rss_entries)
    merged = ensure_canonical(merged)
    for e in merged:
        if e.get("type") not in ("conference", "journal"):
            e["type"] = "conference"
    merged = sort_entries(merged)
    save_entries(merged)


if __name__ == "__main__":
    main()
