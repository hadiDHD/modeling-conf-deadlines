#!/usr/bin/env python3
"""
Crawl4AI Local Docker Agent for Conference Deadlines & Workshops/Tracks.

This script uses a Crawl4AI instance running in local Docker (default: http://localhost:11235)
to crawl conference websites, discover next year's webpage if missing, update submission/abstract
deadlines, and discover workshop and track deadlines.

Usage:
  python scripts/crawl_with_crawl4ai.py [--docker-host localhost] [--port 11235] [--token testtoken] [--dry-run]
"""

import os
import sys
import re
import json
import time
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict
from typing import Any

import requests
import yaml
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

# Path configuration
REPO_ROOT = Path(__file__).resolve().parent.parent
CONF_FILE = REPO_ROOT / "_data" / "conferences.yml"

CRAWL4AI_DEFAULT_HOST = "localhost"
CRAWL4AI_DEFAULT_PORT = 11235
CRAWL4AI_DEFAULT_TOKEN = "testtoken"

DEFAULT_TIMEZONE = "AoE (UTC-12h)"
DEFAULT_SUB = ["SE"]

# Month mapping
MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9, "sept": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

# Main conference list to seed or track
CANONICAL_SERIES = [
    {"title": "MODELS", "link": "https://conf.researchr.org/home/models-2026", "year": 2026, "sub": ["SE"]},
    {"title": "ECMFA", "link": "https://conf.researchr.org/track/ecmfa-2026/ecmfa-2026", "year": 2026, "sub": ["SE"]},
    {"title": "SLE", "link": "https://conf.researchr.org/home/sle-2026", "year": 2026, "sub": ["SE"]},
    {"title": "ER", "link": "https://er2026.org", "year": 2026, "sub": ["DB"]},
    {"title": "POEM", "link": "https://poem-conference.org", "year": 2026, "sub": ["SE"]},
    {"title": "ICSE", "link": "https://conf.researchr.org/home/icse-2026", "year": 2026, "sub": ["SE"]},
    {"title": "ASE", "link": "https://conf.researchr.org/home/ase-2026", "year": 2026, "sub": ["SE"]},
    {"title": "SSBSE", "link": "https://conf.researchr.org/home/ssbse-2026", "year": 2026, "sub": ["SE"]},
    {"title": "ANNSIM", "link": "https://scs.org/annsim/", "year": 2026, "sub": ["SE"]},
    {"title": "MoDELSWARD", "link": "https://modelsward.scitevents.org/", "year": 2026, "sub": ["SE"]},
    {"title": "FASE", "link": "https://etaps.org/2026/cfp/", "year": 2026, "sub": ["SE"]},
]


def ensure_crawl4ai_server(host: str, port: int, token: str) -> bool:
    """Ensure the Crawl4AI docker container is running and healthy."""
    url = f"http://{host}:{port}/crawl"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.post(url, headers=headers, json={"urls": ["https://example.com"]}, timeout=5)
        if r.status_code in (200, 422):
            print(f"[Crawl4AI] Server at http://{host}:{port} is active.")
            return True
    except Exception:
        pass

    print(f"[Crawl4AI] Server at http://{host}:{port} not responding. Attempting to start Docker container...")
    try:
        compose_file = REPO_ROOT / "docker-compose.yml"
        if compose_file.exists():
            subprocess.run(["docker", "compose", "up", "-d"], cwd=str(REPO_ROOT), check=True)
        else:
            subprocess.run([
                "docker", "run", "-d", "--name", "crawl4ai",
                "-p", f"{port}:11235",
                "-e", f"CRAWL4AI_API_TOKEN={token}",
                "unclecode/crawl4ai:latest"
            ], check=True)
        
        for _ in range(15):
            time.sleep(1)
            try:
                r = requests.post(url, headers=headers, json={"urls": ["https://example.com"]}, timeout=3)
                if r.status_code in (200, 422):
                    print(f"[Crawl4AI] Server started successfully at http://{host}:{port}.")
                    return True
            except Exception:
                continue
    except Exception as e:
        print(f"[Crawl4AI] Failed to start Docker container automatically: {e}")
    return False


def crawl_single_url(endpoint: str, headers: dict, url: str) -> dict | None:
    """Crawl a single URL safely."""
    try:
        resp = requests.post(
            endpoint,
            headers=headers,
            json={"urls": [url], "bypass_cache": True, "word_count_threshold": 1},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])
            if results:
                return results[0]
    except Exception:
        pass
    return None


def crawl_urls_batch(
    urls: list[str],
    token: str,
    host: str = CRAWL4AI_DEFAULT_HOST,
    port: int = CRAWL4AI_DEFAULT_PORT,
    batch_size: int = 8,
) -> dict[str, dict]:
    """Crawl a list of URLs using Crawl4AI, falling back to individual crawls if a batch fails."""
    results_map: dict[str, dict] = {}
    endpoint = f"http://{host}:{port}/crawl"
    headers = {"Authorization": f"Bearer {token}"}

    unique_urls = list(dict.fromkeys(urls))
    total_batches = (len(unique_urls) + batch_size - 1) // batch_size

    for i in range(0, len(unique_urls), batch_size):
        batch = unique_urls[i : i + batch_size]
        batch_num = i // batch_size + 1
        print(f"[Crawl4AI] Crawling batch {batch_num}/{total_batches} ({len(batch)} URLs)...")
        try:
            resp = requests.post(
                endpoint,
                headers=headers,
                json={"urls": batch, "bypass_cache": True, "word_count_threshold": 1},
                timeout=60,
            )
            if resp.status_code == 200:
                data = resp.json()
                for res in data.get("results", []):
                    u = res.get("url")
                    if u:
                        results_map[u] = res
            else:
                # Batch failed (e.g. status 400 due to invalid candidate URL in batch) -> retry individually
                print(f"[Crawl4AI] Batch {batch_num} returned {resp.status_code}. Retrying URLs individually...")
                for url in batch:
                    res = crawl_single_url(endpoint, headers, url)
                    if res and res.get("url"):
                        results_map[res["url"]] = res
        except Exception as e:
            print(f"[Crawl4AI] Error in batch {batch_num}: {e}. Retrying individually...")
            for url in batch:
                res = crawl_single_url(endpoint, headers, url)
                if res and res.get("url"):
                    results_map[res["url"]] = res
    return results_map


def parse_date_string(date_str: str) -> str | None:
    """Parse human date strings into YYYY-MM-DD 23:59:59."""
    if not date_str or date_str.strip().upper() == "TBA":
        return None
    
    # Range handling e.g. "Wed 15 Jul - Fri 14 Aug 2026" -> pick end or target date
    # Try Day Mon Year e.g. "Mon 30 Jun 2026" or "30 Jun 2026"
    m = re.search(r"(?:[A-Za-z]+\s+)?(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})", date_str)
    if m:
        day, mon, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        month = MONTHS.get(mon) or MONTHS.get(mon[:3])
        if month and 1 <= day <= 31 and 2020 <= year <= 2035:
            return f"{year}-{month:02d}-{day:02d} 23:59:59"

    # Try Mon Day, Year e.g. "June 30, 2026"
    m = re.search(r"([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})", date_str)
    if m:
        mon, day, year = m.group(1).lower(), int(m.group(2)), int(m.group(3))
        month = MONTHS.get(mon) or MONTHS.get(mon[:3])
        if month and 1 <= day <= 31 and 2020 <= year <= 2035:
            return f"{year}-{month:02d}-{day:02d} 23:59:59"

    # Try YYYY-MM-DD
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", date_str)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 2020 <= year <= 2035 and 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year}-{month:02d}-{day:02d} 23:59:59"

    # Fallback dateutil
    try:
        dt = date_parser.parse(date_str, fuzzy=True)
        if 2020 <= dt.year <= 2035:
            return f"{dt.year}-{dt.month:02d}-{dt.day:02d} 23:59:59"
    except Exception:
        pass
    return None


def generate_next_year_candidate_urls(current_url: str, current_year: int) -> list[str]:
    """Generate potential next year webpage URLs."""
    next_year = current_year + 1
    candidates = []

    curr_yr_str = str(current_year)
    next_yr_str = str(next_year)

    if curr_yr_str in current_url:
        candidates.append(current_url.replace(curr_yr_str, next_yr_str))

    if "conf.researchr.org" in current_url:
        m = re.search(r"conf\.researchr\.org/(?:home|track)/([a-z0-9-]+)", current_url)
        if m:
            slug = m.group(1)
            series = re.sub(r"-\d{4}.*", "", slug)
            candidates.append(f"https://conf.researchr.org/home/{series}-{next_year}")

    m = re.search(r"https?://([a-z0-9-]+)" + curr_yr_str + r"\.org", current_url)
    if m:
        base = m.group(1)
        candidates.append(f"https://{base}{next_yr_str}.org")

    return list(dict.fromkeys(candidates))


def slugify(text: str) -> str:
    """Slugify for entry IDs."""
    text = re.sub(r"[^a-zA-Z0-9\s-]", "", text.lower())
    text = re.sub(r"[\s-]+", "-", text).strip("-")
    return text


def load_existing_entries() -> list[dict]:
    """Load entries from _data/conferences.yml."""
    if not CONF_FILE.exists():
        return []
    with open(CONF_FILE, encoding="utf-8") as f:
        raw = f.read()
    try:
        data = yaml.safe_load(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_entries(entries: list[dict]) -> None:
    """Save clean YAML list to _data/conferences.yml."""
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


def process_researchr_dates_page(
    dates_url: str, crawl_data: dict
) -> tuple[dict[str, dict[str, str]], str | None, str | None]:
    """
    Parse Researchr dates table into track mapping.
    Returns dict: track_name -> {'deadline': ..., 'abstract_deadline': ...}
    """
    html = crawl_data.get("cleaned_html", "")
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE)

    track_dates = defaultdict(dict)
    for row in rows:
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)]
        if len(cells) >= 3:
            date_raw, track_name, event_name = cells[0], cells[1], cells[2]
            parsed_dt = parse_date_string(date_raw)
            if not parsed_dt:
                continue

            event_lower = event_name.lower()
            if "abstract" in event_lower:
                if "abstract_deadline" not in track_dates[track_name]:
                    track_dates[track_name]["abstract_deadline"] = parsed_dt
            elif any(k in event_lower for k in ["paper submission", "submission deadline", "paper deadline", "submission"]):
                if "deadline" not in track_dates[track_name]:
                    track_dates[track_name]["deadline"] = parsed_dt

    for td in track_dates.values():
        if td.get("deadline") and td.get("abstract_deadline") and td["abstract_deadline"] > td["deadline"]:
            print(f"[Warning] Abstract deadline ({td['abstract_deadline']}) > submission deadline ({td['deadline']}) in Researchr track dates. Swapping.")
            td["abstract_deadline"], td["deadline"] = td["deadline"], td["abstract_deadline"]

    return track_dates, None, None


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


def run_crawl_and_update(host: str, port: int, token: str, dry_run: bool = False) -> None:
    """Primary execution pipeline."""
    if not ensure_crawl4ai_server(host, port, token):
        print("[Error] Crawl4AI server is unavailable. Aborting.")
        return

    existing_entries = load_existing_entries()
    print(f"[Loaded] {len(existing_entries)} existing entries.")

    # Gather URLs
    urls_to_crawl = []
    next_year_map: dict[str, dict] = {}

    for entry in existing_entries:
        link = entry.get("link")
        if link:
            urls_to_crawl.append(link)

            if "conf.researchr.org" in link:
                m = re.search(r"conf\.researchr\.org/(?:home|track)/([a-z0-9-]+)", link)
                if m:
                    slug = m.group(1).split("/")[0]
                    urls_to_crawl.append(f"https://conf.researchr.org/dates/{slug}")

            year = entry.get("year")
            if isinstance(year, int):
                for cand in generate_next_year_candidate_urls(link, year):
                    urls_to_crawl.append(cand)
                    next_year_map[cand] = {"parent_entry": entry, "next_year": year + 1}

    print(f"[Crawl4AI] Requesting crawl for {len(set(urls_to_crawl))} target & candidate URLs...")
    crawled_data = crawl_urls_batch(urls_to_crawl, token=token, host=host, port=port)

    # 1. Promote discovered next-year pages
    promoted_entries = []
    for cand_url, info in next_year_map.items():
        res = crawled_data.get(cand_url)
        if res and res.get("status_code") == 200 and res.get("success"):
            meta = res.get("metadata", {})
            title = meta.get("title", "")
            next_yr = info["next_year"]
            if str(next_yr) in title or str(next_yr) in cand_url:
                print(f"[Discovered Next Year Webpage] {info['parent_entry']['title']} {next_yr} -> {cand_url}")
                parent = dict(info["parent_entry"])
                parent["year"] = next_yr
                parent["id"] = re.sub(r"\d{4}", str(next_yr), parent.get("id", ""))
                if not parent["id"].endswith(str(next_yr)):
                    parent["id"] = f"{parent['id']}{next_yr}"
                parent["link"] = cand_url
                parent["deadline"] = "TBA"
                if "abstract_deadline" in parent:
                    parent["abstract_deadline"] = "TBA"
                promoted_entries.append(parent)

    existing_links = {e.get("link") for e in existing_entries}
    for pe in promoted_entries:
        if pe["link"] not in existing_links:
            existing_entries.append(pe)
            existing_links.add(pe["link"])

    # 2. Extract deadlines and discover tracks/workshops
    discovered_tracks = []
    for entry in existing_entries:
        link = entry.get("link")
        if not link:
            continue

        res = crawled_data.get(link)
        if not res or res.get("status_code") != 200:
            continue

        meta = res.get("metadata", {})
        desc_meta = meta.get("description") or meta.get("og:description") or ""

        # Location extraction
        if not entry.get("place"):
            m_place = re.search(r"in\s+([A-Z][a-zA-Z\s]+,\s*[A-Z][a-zA-Z\s]+)", desc_meta)
            if m_place:
                entry["place"] = m_place.group(1).strip()

        # Dates extraction
        if not entry.get("date"):
            m_date = re.search(r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:\s*-\s*(?:[A-Za-z]+\s+)?\d{1,2})?,?\s+\d{4})", desc_meta)
            if m_date:
                entry["date"] = m_date.group(1).strip()

        # Researchr conferences & track discovery
        if "conf.researchr.org" in link:
            m = re.search(r"conf\.researchr\.org/(?:home|track)/([a-z0-9-]+)", link)
            if m:
                slug = m.group(1).split("/")[0]
                dates_url = f"https://conf.researchr.org/dates/{slug}"
                dates_res = crawled_data.get(dates_url)
                if dates_res and dates_res.get("status_code") == 200:
                    track_dates, _, _ = process_researchr_dates_page(dates_url, dates_res)

                    main_keys = ["Research Track", "Research Papers", "Main Track", "Technical Track"]
                    main_updated = False
                    for mk in main_keys:
                        if mk in track_dates:
                            if track_dates[mk].get("deadline"):
                                entry["deadline"] = track_dates[mk]["deadline"]
                            if track_dates[mk].get("abstract_deadline"):
                                entry["abstract_deadline"] = track_dates[mk]["abstract_deadline"]
                            main_updated = True
                            break

                    if not main_updated and track_dates:
                        dls = [td["deadline"] for td in track_dates.values() if "deadline" in td]
                        if dls:
                            dls.sort()
                            entry["deadline"] = dls[0]

                    # Extract all non-main tracks / workshops
                    for trk_name, trk_info in track_dates.items():
                        if trk_name in main_keys or not trk_info.get("deadline"):
                            continue

                        conf_base = entry["title"].split(" - ")[0].replace(" Workshops", "").strip()
                        year_val = entry.get("year", "")
                        sub_title = clean_track_title(conf_base, trk_name)
                        if not sub_title:
                            continue

                        sub_conf_base = sub_title.split(" - ")[0].strip()
                        sub_part = sub_title.split(" - ")[1].strip()
                        sub_id = slugify(f"{sub_conf_base}-{sub_part}-{year_val}")

                        # Find matching track link
                        track_link = None
                        for internal_link in res.get("links", {}).get("internal", []):
                            href = internal_link.get("href", "")
                            text = internal_link.get("text", "")
                            if slugify(sub_part) in slugify(href) or slugify(sub_part) in slugify(text):
                                if "conf.researchr.org" in href or href.startswith("/"):
                                    track_link = href if href.startswith("http") else f"https://conf.researchr.org{href}"
                                    break

                        if not track_link or "povc-2026" in track_link:
                            main_slug = slug
                            trk_slug = slugify(sub_part)
                            track_link = f"https://conf.researchr.org/track/{main_slug}/{main_slug}-{trk_slug}"

                        if not any(e.get("id") == sub_id for e in existing_entries) and not any(e.get("id") == sub_id for e in discovered_tracks) and not any(e.get("title") == sub_title and e.get("year") == year_val for e in existing_entries):
                            trk_entry = {
                                "title": sub_title,
                                "hindex": None,
                                "year": year_val,
                                "id": sub_id,
                                "link": track_link,
                                "deadline": trk_info.get("deadline", "TBA"),
                                "timezone": entry.get("timezone", DEFAULT_TIMEZONE),
                                "date": entry.get("date", ""),
                                "place": entry.get("place", ""),
                                "sub": entry.get("sub", DEFAULT_SUB),
                                "type": "conference",
                            }
                            if trk_info.get("abstract_deadline"):
                                trk_entry["abstract_deadline"] = trk_info["abstract_deadline"]
                            
                            validate_and_fix_deadlines(trk_entry)
                            discovered_tracks.append(trk_entry)

        # Non-Researchr deadline extraction
        else:
            if (entry.get("deadline") or "TBA") == "TBA":
                html_text = res.get("cleaned_html", "")
                parsed_dl = parse_date_string(html_text)
                if parsed_dl:
                    entry["deadline"] = parsed_dl

    if discovered_tracks:
        print(f"[Discovered Workshops/Tracks] Adding {len(discovered_tracks)} track/workshop entries.")
        existing_entries.extend(discovered_tracks)

    # Clean and deduplicate all entries
    deduped = clean_and_deduplicate_entries(existing_entries)

    # Sort entries: upcoming deadlines first
    def sort_key(e):
        dl = e.get("deadline") or ""
        yr = e.get("year") or 0
        t = e.get("title") or ""
        return (dl if dl != "TBA" else "0000", yr, t)

    deduped.sort(key=sort_key, reverse=True)

    if dry_run:
        print(f"[Dry Run] Analyzed and updated {len(deduped)} entries (dry run mode, not saving).")
    else:
        save_entries(deduped)
        print(f"[Success] Successfully saved {len(deduped)} entries to {CONF_FILE}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl conference deadlines & workshops using Crawl4AI on Docker.")
    parser.add_argument("--host", default=CRAWL4AI_DEFAULT_HOST, help="Crawl4AI host (default: localhost)")
    parser.add_argument("--port", type=int, default=CRAWL4AI_DEFAULT_PORT, help="Crawl4AI port (default: 11235)")
    parser.add_argument("--token", default=CRAWL4AI_DEFAULT_TOKEN, help="Crawl4AI API token")
    parser.add_argument("--dry-run", action="store_true", help="Perform crawl without writing changes to disk")
    args = parser.parse_args()

    run_crawl_and_update(host=args.host, port=args.port, token=args.token, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
