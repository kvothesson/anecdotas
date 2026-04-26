"""
ingest_bulk.py — Ingesta masiva de episodios de Anécdotas via Claude API.

Lee data/playlist.json, compara con data/index.json, y procesa los episodios
que faltan: fetch con yt-dlp + análisis con Claude Sonnet + actualización del index.

Uso:
  ANTHROPIC_API_KEY=... python scripts/ingest_bulk.py
  ANTHROPIC_API_KEY=... python scripts/ingest_bulk.py --start 31 --end 60
  ANTHROPIC_API_KEY=... python scripts/ingest_bulk.py --video-id O28oQJUGaq0
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
except ImportError:
    pass

import anthropic

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
EPISODES_DIR = DATA_DIR / "episodes"
PLAYLIST_FILE = DATA_DIR / "playlist.json"
INDEX_FILE = DATA_DIR / "index.json"

ANALYSIS_PROMPT = """Sos un analista del canal de YouTube "Anécdotas" de Nico de Tracy.
Te doy el transcript de un episodio y tenés que generar el objeto `analysis` en JSON.

TRANSCRIPT:
{transcript}

TÍTULO: {title}
NÚMERO DE EPISODIO: {episode_number}

Generá SOLO el JSON del objeto analysis, sin texto adicional, con este esquema exacto:

{{
  "summary": "1-2 oraciones que describen la situación central sin revelar el giro o desenlace",
  "categories": ["etiqueta1", "etiqueta2"],
  "geography": ["Ciudad o país"],
  "era": "contemporánea|años 90|años 80|años 70|dictadura|siglo XX medio|histórico",
  "protagonist_role": "víctima|protagonista|narrador|testigo|observador",
  "emotional_arc": "cómico|dramático|emotivo|absurdo|terror",
  "institutions_involved": [],
  "historical_events": [],
  "archetypes": ["arquetipo1", "arquetipo2"],
  "has_twist": true,
  "credibility": "baja|media|alta|muy alta",
  "intensity": 7
}}

Reglas:
- categories: usá solo estas etiquetas: drogas, judicial, laboral, familia, romance, viaje, robo, policial, salud, burocracia, vecinos, urbano, histórico, migración, barrio, tecnología, generacional, animales, muerte, paranormal, guerra, deporte, corrupción, estafa
- institutions_involved: solo si aplica, de: justicia, policia, salud, educación, obra social, transporte público, correo, municipio, migraciones, militar, iglesia
- historical_events: solo si ocurre en contexto de evento histórico conocido (Cromañón, crisis 2001, Malvinas, dictadura, pandemia, 11-S)
- intensity: 1-10 (1-3 liviano, 4-6 moderado, 7-8 serio, 9-10 extremo)
- Si hay una segunda anécdota (bonus track), agregá al final del JSON:
  "bonus_track": {{
    "summary": "1-2 oraciones sobre la anécdota secundaria",
    "archetypes": ["arquetipo1"],
    "emotional_arc": "cómico|dramático|emotivo|absurdo|terror",
    "intensity": 5
  }}

Respondé ÚNICAMENTE con el JSON, sin markdown, sin explicaciones."""


def parse_vtt(vtt_path: Path) -> str:
    content = vtt_path.read_text(encoding="utf-8")
    lines = content.split("\n")
    texts = []
    seen = set()
    for line in lines:
        line = line.strip()
        if (not line or "-->" in line or line.startswith("WEBVTT")
                or line.startswith("NOTE") or line.startswith("Kind:")
                or line.startswith("Language:") or line.isdigit()):
            continue
        clean = re.sub(r"<[^>]+>", "", line).strip()
        clean = re.sub(r"&nbsp;", " ", clean)
        clean = re.sub(r"Kind:\s*captions\s*Language:\s*\w+", "", clean).strip()
        if clean and clean not in seen:
            seen.add(clean)
            texts.append(clean)
    return " ".join(texts)


def fetch_episode(video_id: str) -> dict | None:
    raw_path = EPISODES_DIR / f"{video_id}_raw.json"
    if raw_path.exists():
        print(f"  [fetch] Ya existe {raw_path.name}, usando cache")
        with open(raw_path, encoding="utf-8") as f:
            return json.load(f)

    url = f"https://www.youtube.com/watch?v={video_id}"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        cmd = [
            "yt-dlp",
            "--write-auto-sub", "--sub-lang", "es",
            "--skip-download", "--write-info-json",
            "--no-playlist",
            "--output", str(tmp_dir / "%(id)s"),
            url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  [fetch] ERROR yt-dlp: {result.stderr[:200]}", file=sys.stderr)
            return None

        info_files = list(tmp_dir.glob("*.info.json"))
        if not info_files:
            print(f"  [fetch] ERROR: no se generó info.json", file=sys.stderr)
            return None

        with open(info_files[0], encoding="utf-8") as f:
            info = json.load(f)

        vtt_files = list(tmp_dir.glob("*.vtt"))
        transcript = parse_vtt(vtt_files[0]) if vtt_files else ""
        if not transcript:
            print(f"  [fetch] ADVERTENCIA: sin subtítulos", file=sys.stderr)

        upload_date = info.get("upload_date", "")
        published_date = (f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
                          if len(upload_date) == 8 else "")

        title = info.get("title", "")
        ep_match = re.search(r"#\s*(\d+)", title)
        episode_number = int(ep_match.group(1)) if ep_match else 0

        data = {
            "id": video_id,
            "episode_number": episode_number,
            "title": title,
            "url": f"https://youtube.com/watch?v={video_id}",
            "published_date": published_date,
            "duration_seconds": int(info.get("duration", 0)),
            "views": info.get("view_count", 0),
            "likes": info.get("like_count", 0),
            "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            "transcript": transcript,
        }

        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return data


def generate_analysis(client: anthropic.Anthropic, raw: dict) -> dict | None:
    transcript = raw.get("transcript", "")
    if not transcript:
        print(f"  [analysis] Sin transcript, saltando análisis", file=sys.stderr)
        return None

    prompt = ANALYSIS_PROMPT.format(
        transcript=transcript[:12000],  # cap para no exceder tokens
        title=raw.get("title", ""),
        episode_number=raw.get("episode_number", 0),
    )

    for attempt in range(3):
        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            text = message.content[0].text.strip()
            # Limpiar posible markdown
            text = re.sub(r"^```json\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            return json.loads(text)
        except json.JSONDecodeError as e:
            print(f"  [analysis] JSON inválido (intento {attempt+1}): {e}", file=sys.stderr)
            if attempt == 2:
                return None
            time.sleep(2)
        except anthropic.RateLimitError:
            print(f"  [analysis] Rate limit, esperando 60s...", file=sys.stderr)
            time.sleep(60)
        except Exception as e:
            print(f"  [analysis] ERROR: {e}", file=sys.stderr)
            if attempt == 2:
                return None
            time.sleep(5)

    return None


def save_episode(raw: dict, analysis: dict, playlist_entry: dict) -> dict:
    episode_number = raw.get("episode_number") or playlist_entry.get("number", 0)

    full = {
        "id": raw["id"],
        "episode_number": episode_number,
        "title": raw["title"],
        "url": raw["url"],
        "published_date": raw["published_date"],
        "duration_seconds": raw["duration_seconds"],
        "views": raw["views"],
        "likes": raw["likes"],
        "thumbnail": raw["thumbnail"],
        "analysis": analysis,
    }

    out_path = EPISODES_DIR / f"{raw['id']}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(full, f, ensure_ascii=False, indent=2)

    return full


def update_index(episode: dict, lock: threading.Lock):
    with lock:
        with open(INDEX_FILE, encoding="utf-8") as f:
            index = json.load(f)
        index = [e for e in index if e["id"] != episode["id"]]
        index.append({k: v for k, v in episode.items()})
        index.sort(key=lambda e: e["episode_number"])
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)


def process_entry(entry, client, index_lock, counters, total):
    video_id = entry["video_id"]
    number = entry["number"]
    title = entry["title"]
    print(f"  --> #{number} {video_id} — {title[:50]}")

    raw = fetch_episode(video_id)
    if raw is None:
        print(f"  [#{number}] SKIP — fetch falló")
        return (number, video_id, "fetch failed")

    analysis = generate_analysis(client, raw)
    if analysis is None:
        print(f"  [#{number}] SKIP — análisis falló")
        return (number, video_id, "analysis failed")

    episode = save_episode(raw, analysis, entry)
    update_index(episode, index_lock)

    with index_lock:
        counters["ok"] += 1
        done = counters["ok"] + counters["errors"]
        geo = ", ".join(analysis.get("geography", []))
        arc = analysis.get("emotional_arc", "?")
        intensity = analysis.get("intensity", "?")
        print(f"  [#{number}] OK ({done}/{total}) — {geo} · {arc} · {intensity}/10")

    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, help="Número de episodio inicial (inclusive)")
    parser.add_argument("--end", type=int, help="Número de episodio final (inclusive)")
    parser.add_argument("--video-id", help="Procesar un video específico")
    parser.add_argument("--workers", type=int, default=4, help="Threads paralelos (default: 4)")
    args = parser.parse_args()

    client = anthropic.Anthropic()

    with open(PLAYLIST_FILE, encoding="utf-8") as f:
        playlist = json.load(f)

    with open(INDEX_FILE, encoding="utf-8") as f:
        index = json.load(f)

    done_ids = {e["id"] for e in index}

    if args.video_id:
        to_process = [e for e in playlist if e["video_id"] == args.video_id]
    else:
        to_process = [e for e in playlist if e["video_id"] not in done_ids]
        if args.start:
            to_process = [e for e in to_process if e["number"] >= args.start]
        if args.end:
            to_process = [e for e in to_process if e["number"] <= args.end]

    print(f"Episodios a procesar: {len(to_process)}")
    print(f"Ya procesados: {len(done_ids)}")
    print(f"Workers: {args.workers}")
    print()

    index_lock = threading.Lock()
    counters = {"ok": 0, "errors": 0}
    errors = []
    total = len(to_process)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(process_entry, entry, client, index_lock, counters, total): entry
            for entry in to_process
        }
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                with index_lock:
                    counters["errors"] += 1
                errors.append(result)

    print(f"\n{'='*50}")
    print(f"Completados: {counters['ok']}/{total}")
    if errors:
        print(f"Errores ({len(errors)}):")
        for num, vid, reason in errors:
            print(f"  #{num} {vid} — {reason}")


if __name__ == "__main__":
    main()
