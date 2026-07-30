#!/usr/bin/env python3
"""
Serve the built site locally and capture high-quality viewport and full-page screenshots
using Playwright. Saves images in static/screenshots/.
"""
import os
import sys
import time
import socket
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = REPO_ROOT / "_site"
SCREENSHOT_DIR = REPO_ROOT / "static" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

class QuietHTTPRequestHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

def run_server(server):
    server.serve_forever()

def main():
    if not (SITE_DIR / "index.html").exists():
        print("[Error] _site/index.html not found. Building site first...")
        os.system(f'python "{REPO_ROOT / "scripts" / "build_site.py"}"')

    handler = lambda *args, **kwargs: QuietHTTPRequestHandler(*args, directory=str(SITE_DIR), **kwargs)
    server = HTTPServer(("127.0.0.1", 8080), handler)
    server_thread = threading.Thread(target=run_server, args=(server,), daemon=True)
    server_thread.start()
    print("[HTTP Server] Serving _site on http://127.0.0.1:8080")

    time.sleep(1)

    captured_paths = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 850},
            device_scale_factor=2,
        )
        page = context.new_page()

        print("[Playwright] Navigating to http://127.0.0.1:8080...")
        page.goto("http://127.0.0.1:8080", wait_until="networkidle")
        page.wait_for_timeout(2000)

        # Viewport Screenshot
        preview_path = SCREENSHOT_DIR / "preview.png"
        page.screenshot(path=str(preview_path), full_page=False)
        captured_paths.append(preview_path)
        print(f"[Screenshot Captured] Viewport: {preview_path}")

        # Full Page Screenshot
        full_path = SCREENSHOT_DIR / "preview-full.png"
        page.screenshot(path=str(full_path), full_page=True)
        captured_paths.append(full_path)
        print(f"[Screenshot Captured] Full Page: {full_path}")

        # Optional Theme Toggle if available
        if page.locator("#theme-toggle").count() > 0:
            page.click("#theme-toggle")
            page.wait_for_timeout(600)
            dark_preview = SCREENSHOT_DIR / "preview-dark.png"
            page.screenshot(path=str(dark_preview), full_page=False)
            captured_paths.append(dark_preview)

        browser.close()

    server.shutdown()
    server.server_close()
    print("\n--- Captured Screenshot Absolute Paths ---")
    for path in captured_paths:
        print(str(path.resolve()))

if __name__ == "__main__":
    main()
