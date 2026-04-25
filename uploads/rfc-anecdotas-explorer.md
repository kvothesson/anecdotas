# RFC: Anécdotas Explorer

## Resumen

Web estática hosteable en GitHub Pages que permite explorar, filtrar y analizar el corpus completo del canal **Anécdotas** de Nico de Tracy (~200 episodios). Las estadísticas de YouTube se actualizan automáticamente vía GitHub Actions sin necesidad de backend.

---

## Stack

| Capa | Tecnología |
|------|-----------|
| Frontend | HTML + vanilla JS (o Astro si se quiere build) |
| Hosting | GitHub Pages |
| Data refresh | GitHub Actions (cron diario) |
| Transcripts | `yt-dlp` + YouTube Transcript API |
| Análisis | Claude API (batch, una vez) |
| Stats live | YouTube Data API v3 (client-side, API key pública restringida por dominio) |

---

## Arquitectura

```
[GitHub Actions - cron diario]
        │
        ▼
  fetch_stats.py
  (YouTube Data API v3)
        │
        ▼
  data/episodes.json  ◄──── commiteado al repo
        │
        ▼
  GitHub Pages sirve
  el JSON como asset estático
        │
        ▼
  Frontend lo fetchea en runtime
```

### ¿Por qué este approach?

- GitHub Pages es 100% estático → no hay backend
- La YouTube Data API tiene cuota gratuita generosa (10k unidades/día)
- GitHub Actions actualiza el JSON una vez por día → stats "casi en vivo"
- No se expone API key sensible (la de stats va en GitHub Secrets, solo corre en Actions)

---

## Contrato de datos

### `data/episodes.json`

Array de objetos con este schema:

```json
[
  {
    "id": "dQw4w9WgXcQ",
    "episode_number": 1,
    "title": "FRANCISQUITO y Los MOGUL",
    "url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
    "published_date": "2020-08-21",
    "duration_seconds": 607,
    "views": 280082,
    "likes": 9700,
    "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
    "transcript": "texto crudo completo del episodio...",
    "analysis": {
      "summary": "Una empleada doméstica consume accidentalmente sustancias de su empleador y termina en un juicio.",
      "categories": ["drogas", "judicial", "laboral"],
      "geography": ["Buenos Aires"],
      "era": "contemporánea",
      "protagonist_role": "víctima",
      "emotional_arc": "cómico",
      "institutions_involved": ["justicia"],
      "historical_events": [],
      "archetypes": ["empleada doméstica", "abogado"],
      "has_twist": true,
      "credibility": "alta",
      "intensity": 6
    }
  }
]
```

### Campos invariantes (nunca cambian, se generan una vez)
`id`, `episode_number`, `title`, `url`, `published_date`, `duration_seconds`, `thumbnail`, `transcript`, `analysis`

### Campos dinámicos (GitHub Actions los actualiza diariamente)
`views`, `likes`

---

## Pipeline de generación (one-time setup)

```
1. fetch_playlist.py
   └── YouTube Data API → lista de video_ids + metadata básica

2. fetch_transcripts.py
   └── yt-dlp / youtube-transcript-api → transcript por video
   └── output: episodes_raw.json

3. analyze.py
   └── Claude API (claude-sonnet-4-6, batch)
   └── input: transcript
   └── output: analysis object
   └── resultado: episodes.json completo

4. commit → repo → GitHub Pages lo sirve
```

---

## Pipeline de actualización (GitHub Actions, diario)

```yaml
# .github/workflows/refresh_stats.yml
on:
  schedule:
    - cron: '0 6 * * *'  # 6am UTC todos los días

jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install google-api-python-client
      - run: python scripts/fetch_stats.py
        env:
          YOUTUBE_API_KEY: ${{ secrets.YOUTUBE_API_KEY }}
      - run: |
          git config user.email "actions@github.com"
          git config user.name "GitHub Actions"
          git add data/episodes.json
          git commit -m "chore: refresh YouTube stats" || exit 0
          git push
```

---

## Frontend — Vistas

### 1. Feed principal (`/`)
- Cards con thumbnail, título, categorías, views, duración
- Filtros: categoría · geografía · arco emocional · era
- Ordenar por: más vistas · más reciente · más intenso

### 2. Episodio (`/episode/:id`)
- Player de YouTube embebido
- Resumen (sin spoiler)
- Tags clickeables
- "Si te gustó esta → #57, #93"
- Transcript scrolleable

### 3. Stats (`/stats`)
- Institución que más aparece
- Geografía (mapa con pins)
- Distribución de arcos emocionales
- Top 10 más vistas vs top 10 más intensas

### 4. Búsqueda semántica (`/search`)
- Búsqueda por texto libre sobre summaries + transcripts
- Filtro por cualquier campo del analysis

---

## Limitaciones conocidas

| Limitación | Mitigación |
|-----------|------------|
| Transcripts no disponibles en todos los videos | Marcar como `transcript: null`, excluir del análisis |
| YouTube API cuota 10k unidades/día | Refresh diario consume ~200 unidades (1 por video), muy por debajo del límite |
| GitHub Pages no tiene servidor → no hay búsqueda full-text nativa | Usar Fuse.js (búsqueda client-side) o índice pre-generado |
| Claude API costo del análisis inicial | ~200 episodios × ~$0.003 ≈ $0.60 total, one-time |

---

## Estructura de archivos del repo

```
anecdotas-explorer/
├── data/
│   └── episodes.json          # el contrato central
├── scripts/
│   ├── fetch_playlist.py
│   ├── fetch_transcripts.py
│   ├── analyze.py
│   └── fetch_stats.py         # corre en Actions
├── .github/
│   └── workflows/
│       └── refresh_stats.yml
├── src/                       # frontend
│   ├── index.html
│   ├── episode.html
│   ├── stats.html
│   └── js/
│       ├── app.js
│       ├── filters.js
│       └── search.js
└── README.md
```

---

## Orden de implementación sugerido

1. `fetch_playlist.py` → tener todos los IDs y metadata
2. `fetch_transcripts.py` → corpus de texto
3. `analyze.py` → enriquecer con Claude
4. Frontend estático con data hardcodeada
5. GitHub Actions para stats dinámicas
6. Deploy en GitHub Pages
