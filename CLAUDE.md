# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

**Anécdotas Explorer** — a static single-page app that catalogs episodes of the YouTube show "Anécdotas" by Nico de Tracy. There is no build step: `index.html` is the entire frontend, deployed directly via GitHub Pages.

## Data architecture

All data lives in `data/`:

- `data/index.json` — array of all episodes with metadata + `analysis` (no transcript). This is what the frontend loads.
- `data/episodes/{VIDEO_ID}.json` — full episode record including `transcript` and `analysis`.
- `data/episodes/{VIDEO_ID}_raw.json` — intermediate file produced by the ingest script (no `analysis`); not served to users.

When adding or updating an episode, both `data/index.json` and `data/episodes/{VIDEO_ID}.json` must be kept in sync.

## Ingesting a new episode

Use the `anecdotas-ingest` skill (triggers automatically when the user pastes a YouTube link or says "ingestar episodio").

Manual steps:
1. Run the fetch script:
   ```bash
   python skills/anecdotas-ingest/scripts/fetch_episode.py \
     --video-id {VIDEO_ID} \
     --out-dir data/episodes
   ```
   Requires `yt-dlp` installed. Produces `data/episodes/{VIDEO_ID}_raw.json`.

2. Read the raw JSON, generate the `analysis` object per the schema in `skills/anecdotas-ingest/SKILL.md`, and save the final JSON to `data/episodes/{VIDEO_ID}.json`.

3. Append the episode (without `transcript`) to `data/index.json`.

## Refreshing YouTube stats

```bash
YOUTUBE_API_KEY=... python scripts/refresh_stats.py
```

Also runs automatically via GitHub Actions daily at 06:00 UTC (`.github/workflows/refresh-stats.yml`), committing any view/like changes back to the repo. Requires `YOUTUBE_API_KEY` as a GitHub secret.

## Frontend

`index.html` is a self-contained vanilla JS + CSS app. Key behaviors:
- Loads `data/index.json` on startup and populates `filteredEps` for the feed.
- Uses [Fuse.js](https://fusejs.io/) (loaded from unpkg CDN) for fuzzy search over title + summary + archetypes.
- Episode detail view fetches the individual `data/episodes/{VIDEO_ID}.json` on demand (to get the transcript).
- Filtering by category, geography, era, emotional arc, and sorting by intensity/views/date are all done client-side.

## Episode JSON contract

See `skills/anecdotas-ingest/SKILL.md` for the full schema. Key `analysis` fields:
- `categories`: vocabulary-controlled tags (`drogas`, `judicial`, `laboral`, etc.)
- `emotional_arc`: `cómico | dramático | emotivo | absurdo | terror`
- `protagonist_role`: `víctima | protagonista | narrador | testigo | observador`
- `credibility`: `baja | media | alta | muy alta`
- `intensity`: 1–10 integer
- `era`: `contemporánea | años 90 | años 80 | años 70 | dictadura | siglo XX medio | histórico`
