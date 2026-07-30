#!/usr/bin/env python3
"""
Sync _data/conferences.yml from upstream (already merged by workflow) with
Researchr API, Researchr dates pages (scraped), and optionally WikiCFP RSS.
Idempotent; only adds/updates. No hardcoded deadlines.
"""
from __future__ import annotations

import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

# Path to data file (repo root = cwd when run from workflow)
DATA_DIR = Path(__file__).resolve().parent.parent
CONF_FILE = DATA_DIR / "_data" / "conferences.yml"

# Researchr API and dates pages
RESEARCHR_API = "https://researchr.org/api/search/conference"
RESEARCHR_DATES_BASE = "https://conf.researchr.org/dates"
RESEARCHR_HOME_PREFIX = "https://conf.researchr.org/home/"
RESEARCHR_TRACK_PREFIX = "https://conf.researchr.org/track/"

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
CURRENT_YEAR = datetime.now(timezone.utc).year
YEAR_MIN = CURRENT_YEAR
YEAR_MAX = CURRENT_YEAR + 2

# Canonical list: every conference and journal that must appear on the page.
# If the API doesn't return them, these are added with TBA so they still show.
# Links are the authoritative URLs you requested.
CANONICAL_CONFERENCES = [
    {"title": "MODELS", "id": "models2026", "link": "https://conf.researchr.org/home/models-2026", "year": 2026, "sub": "SE"},
    {"title": "MODELS - Workshops", "id": "models-workshops-2026", "link": "https://conf.researchr.org/track/models-2026/models-2026-workshops", "year": 2026, "sub": "SE"},
    {"title": "ECMFA", "id": "ecmfa2026", "link": "https://conf.researchr.org/track/ecmfa-2026/ecmfa-2026", "year": 2026, "sub": "SE"},
    {"title": "SLE", "id": "sle2026", "link": "https://conf.researchr.org/home/sle-2026", "year": 2026, "sub": "SE"},
    {"title": "ER", "id": "er2026", "link": "https://er2026.org", "year": 2026, "sub": "DB"},
    {"title": "POEM", "id": "poem2026", "link": "https://poem-conference.org", "year": 2026, "sub": "SE"},
    {"title": "ICSE", "id": "icse2026", "link": "https://conf.researchr.org/home/icse-2026", "year": 2026, "sub": "SE"},
    {"title": "ASE", "id": "ase2026", "link": "https://conf.researchr.org/home/ase-2026", "year": 2026, "sub": "SE"},
    {"title": "SSBSE", "id": "ssbse2026", "link": "https://conf.researchr.org/home/ssbse-2026", "year": 2026, "sub": "SE"},
    {"title": "ANNSIM", "id": "annsim2026", "link": "https://scs.org/annsim/", "year": 2026, "sub": "SE"},
    {"title": "MoDELSWARD", "id": "modelsward2026", "link": "https://modelsward.scitevents.org/", "year": 2026, "sub": "SE"},
    {"title": "FASE", "id": "fase2026", "link": "https://etaps.org/2026/cfp/", "year": 2026, "sub": "SE"},
    {"title": "FSE", "id": "fse2027", "link": "https://conf.researchr.org/home/fse-2027", "year": 2027, "sub": "SE"},
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


# Month name to number for parsing Researchr dates (e.g. "Fri 27 Mar 2026")
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def researchr_slug_from_link(link: str) -> str | None:
    """Extract conference slug from a Researchr URL for use with /dates/{slug}."""
    if not link:
        return None
    link = link.rstrip("/")
    if link.startswith(RESEARCHR_HOME_PREFIX):
        rest = link[len(RESEARCHR_HOME_PREFIX) :]
        return rest.split("/")[0] if "/" in rest else rest
    if link.startswith(RESEARCHR_TRACK_PREFIX):
        # e.g. .../track/models-2026/models-2026-workshops -> models-2026
        rest = link[len(RESEARCHR_TRACK_PREFIX) :]
        return rest.split("/")[0] if "/" in rest else rest
    return None


def fetch_researchr_dates_table(slug: str) -> list[tuple[str, str, str]]:
    """
    Fetch conf.researchr.org/dates/{slug} and parse table rows.
    Returns list of tuples: (date_raw, track_name, event_name).
    """
    url = f"{RESEARCHR_DATES_BASE}/{slug}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT if "_USER_AGENT" in globals() else "ConferenceSync/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return []
    
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE)
    parsed_rows = []
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        if len(cells) < 3:
            continue
        date_raw = re.sub(r"<[^>]+>", "", cells[0]).strip()
        track_name = re.sub(r"<[^>]+>", "", cells[1]).strip()
        event_name = re.sub(r"<[^>]+>", "", cells[2]).strip()
        parsed_rows.append((date_raw, track_name, event_name))
    return parsed_rows


def _parse_date_tuple(s: str) -> tuple[int, int, int] | None:
    m = re.search(r"\w+\s+(\d{1,2})\s+(\w{3})\s+(\d{4})", s.strip())
    if not m:
        return None
    day, mon, year = int(m.group(1)), m.group(2).lower()[:3], int(m.group(3))
    month = _MONTHS.get(mon)
    if not month:
        return None
    return (year, month, day)


_SLUG_DATES_CACHE: dict[str, list[tuple[str, str, str]]] = {}


def get_researchr_dates_for_slug(slug: str) -> list[tuple[str, str, str]]:
    if slug not in _SLUG_DATES_CACHE:
        _SLUG_DATES_CACHE[slug] = fetch_researchr_dates_table(slug)
    return _SLUG_DATES_CACHE[slug]


def fetch_deadline_from_researchr_dates(slug: str, title: str | None = None) -> tuple[str | None, str | None]:
    """
    Fetch conf.researchr.org/dates/{slug} and parse submission deadlines.
    Returns (deadline, abstract_deadline) or (None, None).
    
    When title represents a sub-track, matches that specific track name on the dates page.
    When title is a main track, matches main track keys or primary submission deadline.
    """
    rows = get_researchr_dates_for_slug(slug)
    if not rows:
        return None, None

    subtrack_target = None
    if title and " - " in title:
        conf_base, raw_sub = title.split(" - ", 1)
        subtrack_target = raw_sub.strip()

    def clean_norm(s: str) -> str:
        if not s:
            return ""
        s = s.lower()
        s = re.sub(r'\b(?:icse|ase|models|sle|ecmfa|er|fse|issta|sosp|osdi|asplos|pldi|popl|oopsla|splash)\b', '', s)
        s = re.sub(r'\b\d{4}\b', '', s)
        return re.sub(r'[^a-z0-9]', '', s)

    paper_candidates = []
    abstract_candidates = []

    for date_raw, track_name, event_name in rows:
        parsed_dt = _parse_date_tuple(date_raw)
        if not parsed_dt:
            continue
        y, m, d = parsed_dt
        dt_str = f"{y}-{m:02d}-{d:02d} 23:59:59"
        
        event_lower = event_name.lower()

        # Skip notification, camera-ready, acceptance, responses/rebuttals, etc.
        if any(k in event_lower for k in ["camera ready", "camera-ready", "notification", "response", "rebuttal", "acceptance", "accepted", "author response", "co-located", "proposal", "emse", "stage 2", "stage ii", "post-conference"]):
            continue

        if subtrack_target:
            target_cn = clean_norm(subtrack_target)
            track_cn = clean_norm(track_name)
            is_match = (
                target_cn == track_cn or
                (target_cn in track_cn and len(target_cn) >= 5) or
                (track_cn in target_cn and len(track_cn) >= 5)
            )
            if not is_match:
                continue
        else:
            main_keys = ["research track", "research papers", "main track", "technical track"]
            is_main = (
                any(k in track_name.lower() for k in main_keys) or
                clean_norm(track_name) == clean_norm(slug)
            )
            if not is_main:
                continue

        if "abstract" in event_lower:
            abstract_candidates.append(dt_str)
        elif any(k in event_lower for k in ["paper submission", "submission deadline", "paper deadline", "submission"]):
            paper_candidates.append(dt_str)

    paper_candidates.sort()
    abstract_candidates.sort()
    deadline = paper_candidates[0] if paper_candidates else None
    abstract_deadline = abstract_candidates[0] if abstract_candidates else None

    if deadline and abstract_deadline and abstract_deadline > deadline:
        print(f"[Warning] Abstract deadline ({abstract_deadline}) is after submission deadline ({deadline}) for '{title or slug}'. Swapping.")
        abstract_deadline, deadline = deadline, abstract_deadline

    return deadline, abstract_deadline


# --- Non-Researchr conference deadline fetchers (timeout 10s) ---
FETCH_TIMEOUT = 10
_USER_AGENT = "ConferenceSync/1.0 (https://github.com/hadiDHD/modeling-conf-deadlines)"


def _fetch_html(url: str) -> str | None:
    """Fetch URL and return decoded HTML or None. Uses FETCH_TIMEOUT."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _parse_deadline_from_text(html: str) -> str | None:
    """
    Parse HTML/text for a submission deadline. Prefer dates near 'paper submission',
    'abstract submission', or 'deadline'. Returns 'YYYY-MM-DD 23:59:59' or None.
    """
    text = re.sub(r"<[^>]+>", " ", html).replace("&nbsp;", " ")
    # Normalize whitespace and lower for context
    text_lower = " ".join(text.split()).lower()
    candidates = []  # (y, m, d, score); higher score = better context
    # YYYY-MM-DD
    for m in re.finditer(r"(\d{4})-(\d{2})-(\d{2})", text):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2020 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
            start = max(0, m.start() - 80)
            end = min(len(text_lower), m.end() + 80)
            ctx = text_lower[start:end]
            score = 0
            if "paper submission" in ctx or "submission deadline" in ctx:
                score = 2
            elif "abstract submission" in ctx or "deadline" in ctx:
                score = 1
            candidates.append((y, mo, d, score))
    # Month DD, YYYY or DD Month YYYY (capture month for DD Month YYYY)
    months_pat = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    months_cap = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    for m in re.finditer(rf"{months_pat}\s+(\d{{1,2}}),?\s+(\d{{4}})", text_lower):
        parts = m.group(0).split()
        if len(parts) < 3:
            continue
        mon_str, day_str, year_str = parts[0], parts[1].replace(",", ""), parts[2]
        month = _MONTHS.get(mon_str[:3])
        if not month:
            continue
        try:
            day, year = int(day_str), int(year_str)
        except ValueError:
            continue
        if 2020 <= year <= 2030 and 1 <= day <= 31:
            start = max(0, m.start() - 80)
            end = min(len(text_lower), m.end() + 80)
            ctx = text_lower[start:end]
            score = 0
            if "paper submission" in ctx or "submission deadline" in ctx:
                score = 2
            elif "abstract submission" in ctx or "deadline" in ctx:
                score = 1
            candidates.append((year, month, day, score))
    for m in re.finditer(rf"(\d{{1,2}})\s+{months_cap}\s+(\d{{4}})", text_lower):
        day, year = int(m.group(1)), int(m.group(3))
        mon_str = m.group(2)
        month = _MONTHS.get(mon_str[:3])
        if not month:
            continue
        if 2020 <= year <= 2030 and 1 <= day <= 31:
            start = max(0, m.start() - 80)
            end = min(len(text_lower), m.end() + 80)
            ctx = text_lower[start:end]
            score = 0
            if "paper submission" in ctx or "submission deadline" in ctx:
                score = 2
            elif "abstract submission" in ctx or "deadline" in ctx:
                score = 1
            candidates.append((year, month, day, score))
    if not candidates:
        return None
    # Prefer higher score, then earliest date
    candidates.sort(key=lambda c: (-c[3], c[0], c[1], c[2]))
    y, mo, d = candidates[0][0], candidates[0][1], candidates[0][2]
    try:
        datetime(y, mo, d)
        return f"{y}-{mo:02d}-{d:02d} 23:59:59"
    except ValueError:
        return None


def fetch_deadline_poem() -> str | None:
    """POEM: poem-conference.org. Try main page and common CFP/dates paths."""
    for path in ["", "/cfp", "/dates", "/2026"]:
        url = "https://poem-conference.org" + path
        html = _fetch_html(url)
        if html and ("deadline" in html.lower() or "submission" in html.lower() or "2026" in html):
            dl = _parse_deadline_from_text(html)
            if dl:
                return dl
    return None


def fetch_deadline_modelsward() -> str | None:
    """MoDELSWARD: modelsward.scitevents.org."""
    for path in ["", "/ImportantDates.aspx", "/Dates.aspx", "/CFP.aspx"]:
        url = "https://modelsward.scitevents.org" + path
        html = _fetch_html(url)
        if html:
            dl = _parse_deadline_from_text(html)
            if dl:
                return dl
    return None


def fetch_deadline_fase() -> str | None:
    """FASE (ETAPS): etaps.org. FASE is part of ETAPS; check current year page."""
    url = "https://etaps.org/2026/"
    html = _fetch_html(url)
    if not html:
        return None
    # ETAPS page may list FASE; look for submission/deadline and a date
    dl = _parse_deadline_from_text(html)
    if dl:
        return dl
    # Try FASE-specific link if present
    for m in re.finditer(r'href="([^"]*fase[^"]*)"', html, re.I):
        u = m.group(1)
        if u.startswith("http"):
            next_url = u
        else:
            next_url = "https://etaps.org" + (u if u.startswith("/") else "/" + u)
        h2 = _fetch_html(next_url)
        if h2:
            dl = _parse_deadline_from_text(h2)
            if dl:
                return dl
    return None


def fetch_deadline_er() -> str | None:
    """ER: er2026.org."""
    html = _fetch_html("https://er2026.org")
    if html:
        return _parse_deadline_from_text(html)
    return None


def fetch_deadline_ecmfa() -> str | None:
    """ECMFA: ecmfa.org."""
    html = _fetch_html("https://www.ecmfa.org/")
    if not html:
        html = _fetch_html("https://ecmfa.org/")
    if html:
        return _parse_deadline_from_text(html)
    return None


def fetch_deadline_annsim() -> str | None:
    """ANNSIM: scs.org/annsim. Page states e.g. 'Paper Submission Deadline: January 25, 2026'."""
    html = _fetch_html("https://scs.org/annsim/")
    if html:
        return _parse_deadline_from_text(html)
    return None


# Map link domain (or path) to fetcher for TBA conferences
_NON_RESEARCHR_FETCHERS: list[tuple[str, callable]] = [
    ("poem-conference.org", fetch_deadline_poem),
    ("modelsward.scitevents.org", fetch_deadline_modelsward),
    ("etaps.org", fetch_deadline_fase),
    ("er2026.org", fetch_deadline_er),
    ("ecmfa.org", fetch_deadline_ecmfa),
    ("scs.org/annsim", fetch_deadline_annsim),
]


def fetch_deadline_from_non_researchr(link: str) -> str | None:
    """If link matches a known non-Researchr domain, run its fetcher and return deadline or None."""
    if not link:
        return None
    link_lower = link.lower().rstrip("/")
    for domain, fetcher in _NON_RESEARCHR_FETCHERS:
        if domain in link_lower:
            try:
                return fetcher()
            except Exception:
                pass
    return None


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
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError:
        try:
            data = yaml.safe_load(_normalize_yaml_list(raw))
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
            # Do not overwrite journal entries with API data (API is conference-only)
            if e.get("type") != "journal":
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
    channel = root.find("channel") or root.find("{http://purl.org/rss/1.0/}channel")
    if channel is None:
        channel = root
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


def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9\s-]", "", text.lower())
    text = re.sub(r"[\s-]+", "-", text).strip("-")
    return text


def clean_track_title(conf_base: str, trk_name: str) -> str | None:
    base_clean = conf_base.replace(" Workshops", "").strip()
    trk = trk_name.strip()
    acronyms = ["MODELS Workshops", "MODELS", "ICSE", "ASE", "ER", "ECMFA", "SLE", "FSE", "RE", "SPLASH", "SSBSE", "POEM", "FASE", "ANNSIM", "MoDELSWARD", conf_base, base_clean]
    acronym_pattern = "|".join(re.escape(a) for a in acronyms)
    
    pattern = rf"^(?:{acronym_pattern})\b[\s\-_:]*(?:\d{{4}}\b)?[\s\-_:]*"
    trk_stripped = re.sub(pattern, "", trk, flags=re.IGNORECASE).strip()
    trk_stripped = re.sub(r"^\d{4}\b[\s\-_:]*", "", trk_stripped).strip()
    trk_stripped = re.sub(r"[\s\-_:]*\b\d{4}$", "", trk_stripped).strip()

    if not trk_stripped or trk_stripped.lower() == base_clean.lower():
        return None
        
    if trk_stripped.lower() in ["research track", "research papers", "main track", "technical track"]:
        return None
        
    return f"{base_clean} - {trk_stripped}"


def clean_entry_title(title: str) -> str:
    if not title:
        return ""
    if " - " in title:
        conf_base, trk_name = title.split(" - ", 1)
        cleaned = clean_track_title(conf_base, trk_name)
        if cleaned:
            return cleaned
        base_clean = conf_base.replace(" Workshops", "").strip()
        return base_clean
    return title.strip()


def fix_misleading_link(entry: dict) -> None:
    link = entry.get("link", "")
    title = entry.get("title", "")
    year = entry.get("year", 2026)
    
    if "povc-2026" in link and "POVC" not in title.upper():
        conf_base = title.split(" - ")[0].replace(" Workshops", "").strip()
        main_slug = f"{conf_base.lower()}-{year}"
        sub_part = title.split(" - ")[1] if " - " in title else ""
        if sub_part:
            trk_slug = slugify(sub_part)
            entry["link"] = f"https://conf.researchr.org/track/{main_slug}/{main_slug}-{trk_slug}"
        else:
            entry["link"] = f"https://conf.researchr.org/home/{main_slug}"


def validate_and_fix_deadlines(entry: dict) -> None:
    dl = entry.get("deadline")
    adl = entry.get("abstract_deadline")
    title = entry.get("title", "Unknown")
    
    if not dl or not adl or dl == "TBA" or adl == "TBA":
        return
        
    if adl > dl:
        print(f"[Warning] Abstract deadline ({adl}) is after submission deadline ({dl}) for '{title}'. Swapping.")
        entry["abstract_deadline"], entry["deadline"] = dl, adl


def clean_and_deduplicate_entries(entries: list[dict]) -> list[dict]:
    cleaned_map: dict[tuple[str, int | None], dict] = {}
    canonical_ids = {
        "models2026", "models-workshops2026", "icse2026", "ase2026", "sle2026",
        "er2026", "ecmfa2026", "poem2026", "ssbse2026", "annsim2026",
        "modelsward2026", "fase2026", "sosym", "jss", "emse", "tosem",
        "tse", "jot", "smpat"
    }

    for e in entries:
        title = e.get("title", "")
        year = e.get("year")
        
        new_title = clean_entry_title(title)
        if new_title:
            e["title"] = new_title
            
        fix_misleading_link(e)
        validate_and_fix_deadlines(e)
        
        if e.get("id") not in canonical_ids:
            conf_base = e["title"].split(" - ")[0].strip()
            sub_part = e["title"].split(" - ")[1] if " - " in e["title"] else ""
            if sub_part:
                e["id"] = slugify(f"{conf_base}-{sub_part}-{year}")
            else:
                e["id"] = slugify(f"{conf_base}-{year}")

        key = (e["title"], e.get("year"))
        if key not in cleaned_map:
            cleaned_map[key] = e
        else:
            existing = cleaned_map[key]
            if (existing.get("deadline") == "TBA" or not existing.get("deadline")) and e.get("deadline") and e["deadline"] != "TBA":
                existing["deadline"] = e["deadline"]
            if not existing.get("abstract_deadline") and e.get("abstract_deadline"):
                existing["abstract_deadline"] = e["abstract_deadline"]
            if "povc-2026" in existing.get("link", "") and "povc-2026" not in e.get("link", ""):
                existing["link"] = e["link"]

    return list(cleaned_map.values())


def sort_entries(entries: list[dict]) -> list[dict]:
    """Sort by deadline descending (upcoming first), then by year, then title."""
    def key(e):
        d = e.get("deadline") or ""
        y = e.get("year") or 0
        t = e.get("title") or ""
        return (d if d != "TBA" else "0000", y, t)
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
    """Ensure every canonical conference and journal appears. Add with TBA if missing.
    If an entry with the same id already exists, update its link (and canonical fields)
    so that corrected canonical links (e.g. Researchr track URL) replace old ones."""
    by_link = {e.get("link"): e for e in merged}
    by_id = {e.get("id"): e for e in merged}
    out = list(merged)
    for c in CANONICAL_CONFERENCES:
        link = c["link"]
        cid = c.get("id")
        existing = by_id.get(cid) if cid else None
        if existing and existing.get("link") != link:
            # Same conference, link changed (e.g. ecmfa.org -> Researchr track): update in place
            old_link = existing.get("link")
            existing["link"] = link
            if old_link and old_link in by_link:
                del by_link[old_link]
            by_link[link] = existing
        elif link not in by_link:
            entry = canonical_entry(c)
            out.append(entry)
            by_link[link] = entry
            if c.get("id"):
                by_id[c["id"]] = entry
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
            # Ensure journals show Rolling submission; do not overwrite deadline with non-journal data
            if not e.get("note"):
                e["note"] = "Rolling submission"
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

    # Update deadlines from Researchr dates pages (no hardcoded list).
    # Since Researchr dates pages are the absolute source of truth, we always want to sync with them.
    for e in merged:
        if e.get("type") != "conference":
            continue
        link = e.get("link")
        slug = researchr_slug_from_link(link) if link else None
        if not slug:
            continue
        deadline, abstract_deadline = fetch_deadline_from_researchr_dates(slug, title=e.get("title"))
        if deadline:
            e["deadline"] = deadline
            if abstract_deadline:
                e["abstract_deadline"] = abstract_deadline
            else:
                e.pop("abstract_deadline", None)

    # Fill remaining TBA conferences from non-Researchr sites (per-domain fetchers)
    for e in merged:
        if e.get("type") != "conference":
            continue
        if (e.get("deadline") or "").strip() != "TBA":
            continue
        link = e.get("link")
        try:
            deadline = fetch_deadline_from_non_researchr(link)
            if deadline:
                e["deadline"] = deadline
        except Exception:
            pass  # do not fail the whole sync if one fetch fails

    merged = clean_and_deduplicate_entries(merged)
    merged = sort_entries(merged)
    save_entries(merged)


if __name__ == "__main__":
    main()
