"""
refresh_stats.py — actualiza views/likes en data/index.json y data/episodes/*.json
usando la YouTube Data API v3.

Requiere: YOUTUBE_API_KEY en env (GitHub secret en CI, .env local).
"""

import json
import os
import sys
from pathlib import Path
import requests

API_KEY = os.environ.get("YOUTUBE_API_KEY")
if not API_KEY:
    print("ERROR: YOUTUBE_API_KEY no definida", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).parent.parent
INDEX_PATH = ROOT / "data" / "index.json"
EPISODES_DIR = ROOT / "data" / "episodes"

def fetch_stats(video_ids: list[str]) -> dict:
    """Devuelve {video_id: {views, likes}} para hasta 50 IDs."""
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "statistics",
        "id": ",".join(video_ids),
        "key": API_KEY,
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    result = {}
    for item in r.json().get("items", []):
        vid = item["id"]
        stats = item.get("statistics", {})
        result[vid] = {
            "views": int(stats.get("viewCount", 0)),
            "likes": int(stats.get("likeCount", 0)),
        }
    return result

def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

def main():
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    ids = [ep["id"] for ep in index]

    # YouTube API acepta hasta 50 IDs por request
    stats_map = {}
    for batch in chunks(ids, 50):
        stats_map.update(fetch_stats(batch))

    updated = 0
    for ep in index:
        s = stats_map.get(ep["id"])
        if s and (ep.get("views") != s["views"] or ep.get("likes") != s["likes"]):
            ep["views"] = s["views"]
            ep["likes"] = s["likes"]
            updated += 1

            # Actualizar también el JSON individual si existe
            ep_path = EPISODES_DIR / f"{ep['id']}.json"
            if ep_path.exists():
                full = json.loads(ep_path.read_text(encoding="utf-8"))
                full["views"] = s["views"]
                full["likes"] = s["likes"]
                ep_path.write_text(json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8")

    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Stats actualizadas: {updated}/{len(ids)} episodios modificados.")

if __name__ == "__main__":
    main()
