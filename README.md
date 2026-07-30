# Modeling Conference Deadlines

Countdown timers for **modeling, software engineering, and conceptual modeling** conference deadlines.

**Live site:** [hadiDHD.github.io/modeling-conf-deadlines](https://hadiDHD.github.io/modeling-conf-deadlines)

## Running the Website Locally

### Option 1: Docker Compose (Recommended)

Simply start Docker Compose to spin up both the **website** and the **Crawl4AI crawler service**:

```bash
docker compose up -d
```

- **Website**: Open [http://localhost:4000](http://localhost:4000) in your browser.
- **Crawl4AI Service**: Running on `http://localhost:11235`.

### Option 2: Python / Jekyll Locally

If you prefer running without Docker:

```bash
# Build the static site
python scripts/build_site.py

# Serve locally at http://localhost:8000
python -m http.server 8000 --directory _site
```

---

## Crawl4AI Local Docker Agent

To update upcoming deadlines, discover next year's conference webpages, and fetch workshop/track dates using **Crawl4AI**:

1. Ensure Docker services are running:
   ```bash
   docker compose up -d
   ```
2. Install Python dependencies:
   ```bash
   pip install -r scripts/requirements.txt
   ```
3. Run the Crawl4AI Agent:
   ```bash
   python scripts/crawl_with_crawl4ai.py
   ```

The agent will:
- Crawl each conference webpage.
- Probe and discover next year's webpage (e.g. ICSE 2027, FASE 2027) if missing.
- Extract submission and abstract deadlines for main tracks, workshops, and co-located events.
- Update `_data/conferences.yml`.

---

## GitHub Pages Setup

This site is built with **GitHub Actions** (the `github-pages` gem doesn't satisfy GitHub's built-in build).

1. Go to **Settings** → **Pages** in this repo.
2. Under **Build and deployment** → **Source**, choose **GitHub Actions** (not "Deploy from a branch").
3. Push to `main` (or run the "Deploy Jekyll to GitHub Pages" workflow manually). The workflow builds Jekyll with `bundle exec jekyll build` and deploys to Pages.
4. Site URL: **https://hadiDHD.github.io/modeling-conf-deadlines/**

---

## Auto-Sync

This fork automatically updates `_data/conferences.yml`:

- **Daily** sync from upstream [judithmichael/modeling-conf-deadlines](https://github.com/judithmichael/modeling-conf-deadlines)
- **Researchr API** — deadlines for MODELS, ECMFA, SLE, ER, POEM, ICSE, ASE, SSBSE, FASE, MoDELSWARD, ANNSIM, and others
- **Optional** [WikiCFP](http://www.wikicfp.com/) RSS for software-engineering CFPs

Runs on [GitHub Actions](.github/workflows/sync-deadlines.yml) (schedule + manual trigger).

---

## Contributing

To add or update a deadline manually:

1. Edit `_data/conferences.yml`
2. Use the fields: `title`, `year`, `id`, `link`, `deadline`, `timezone`, `date`, `place`, `sub`
   - Timezone strings: [momentjs.com/timezone](https://momentjs.com/timezone/)
3. Optionally add `note` and `abstract_deadline` for separate abstract deadlines
4. Open a pull request

---

## License

[MIT](LICENSE)
