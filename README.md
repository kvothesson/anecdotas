# Anécdotas Explorer

Explorador de episodios del canal [Anécdotas](https://www.youtube.com/@NicodeTracy) de Nico de Tracy.

Permite buscar, filtrar y explorar más de 270 episodios por categoría, geografía, época, arco emocional e intensidad.

**→ [Ver la app](https://kvothesson.github.io/anecdotas/)**

---

## Stack

- Frontend: HTML + JS vanilla, sin build step. Se despliega directo desde GitHub Pages.
- Búsqueda: [Fuse.js](https://fusejs.io/) para fuzzy search client-side.
- Datos: JSONs estáticos en `data/`. El frontend carga `data/index.json` al inicio y fetchea el detalle de cada episodio on demand.
- Stats: GitHub Actions actualiza vistas y likes diariamente con la YouTube Data API.

---

## Cómo se ingirió el contenido

271 episodios fueron procesados en dos fases usando un pipeline de dos etapas:

```
YouTube → yt-dlp → {VIDEO_ID}_raw.json → Claude (análisis) → {VIDEO_ID}.json
```

**Fase 1 — Claude Code skill** (episodios 1-30): procesamiento episodio por episodio, gratis pero limitado por los rate limits de sesión (~14 episodios por sesión, gaps de horas entre sesiones). Sirvió para validar el schema y detectar edge cases.

**Fase 2 — API directa** (episodios 31-271): bulk script llamando a la API de Claude. 228 episodios procesados en 57 minutos continuos por $4.16 en total (~$0.018 por episodio).

Los aprendizajes detallados del proceso están en [docs/aprendizajes-procesamiento-video-llm.md](docs/aprendizajes-procesamiento-video-llm.md).

---

## Agregar un episodio

```bash
python skills/anecdotas-ingest/scripts/fetch_episode.py \
  --video-id {VIDEO_ID} \
  --out-dir data/episodes
```

Requiere `yt-dlp` instalado. Genera `data/episodes/{VIDEO_ID}_raw.json`. Luego usar la skill `anecdotas-ingest` en Claude Code para generar el análisis y actualizar `data/index.json`.

## Actualizar stats

```bash
YOUTUBE_API_KEY=... python scripts/refresh_stats.py
```

También corre automáticamente vía GitHub Actions todos los días a las 06:00 UTC.
