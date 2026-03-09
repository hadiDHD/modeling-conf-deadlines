# Modeling Conference Deadlines

Countdown timers for **modeling, software engineering, and conceptual modeling** conference deadlines.

**Live site:** [hadiDHD.github.io/modeling-conf-deadlines](https://hadiDHD.github.io/modeling-conf-deadlines)

## GitHub Pages setup

This site is built with **GitHub Actions** (the `github-pages` gem doesn't satisfy GitHub's built-in build).

1. Go to **Settings** → **Pages** in this repo.
2. Under **Build and deployment** → **Source**, choose **GitHub Actions** (not "Deploy from a branch").
3. Push to `main` (or run the "Deploy Jekyll to GitHub Pages" workflow manually). The workflow builds Jekyll with `bundle exec jekyll build` and deploys to Pages.
4. Site URL: **https://hadiDHD.github.io/modeling-conf-deadlines/**

## Auto-sync

This fork automatically updates `_data/conferences.yml`:

- **Daily** sync from upstream [judithmichael/modeling-conf-deadlines](https://github.com/judithmichael/modeling-conf-deadlines)
- **Researchr API** — deadlines for MODELS, ECMFA, SLE, ER, POEM, ICSE, ASE, SSBSE, FASE, MoDELSWARD, ANNSIM, and others
- **Optional** [WikiCFP](http://www.wikicfp.com/) RSS for software-engineering CFPs

Runs on [GitHub Actions](.github/workflows/sync-deadlines.yml) (schedule + manual trigger). No crawlers; public repo = free.

## Contributing

Contributions are welcome.

To add or update a deadline manually:

1. Edit `_data/conferences.yml`
2. Use the fields: `title`, `year`, `id`, `link`, `deadline`, `timezone`, `date`, `place`, `sub`
   - Timezone strings: [momentjs.com/timezone](https://momentjs.com/timezone/)
3. Optionally add `note` and `abstract_deadline` for separate abstract deadlines
4. Open a pull request

## Upstream & forks

- **Upstream:** [judithmichael/modeling-conf-deadlines](https://github.com/judithmichael/modeling-conf-deadlines)
- [PL/SE deadlines](https://madhunimmo.github.io/plse-deadlines?sub=SE,PL) by @MadhuNimmo

## License

[MIT](LICENSE)
