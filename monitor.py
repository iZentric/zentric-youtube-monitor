from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yt_dlp

CHANNELS = {
    "Zentric Minecraft": "https://www.youtube.com/channel/UCBoZcTLayAUgYTPsyrStiLg/videos",
    "Klorna": "https://www.youtube.com/@Klorna1/videos",
    "Jocuri Horror": "https://www.youtube.com/@JocuriHorrorSky/videos",
    "Valeriu Coadă": "https://www.youtube.com/@valeriucoada/videos",
}


def fetch_channel(name: str, url: str) -> dict:
    options = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "playlistend": 15,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = []
    for item in (info.get("entries") or []):
        if not item or not item.get("id"):
            continue
        entries.append({
            "video_id": item.get("id"),
            "title": item.get("title"),
            "published": item.get("upload_date"),
            "duration": item.get("duration"),
            "url": f"https://www.youtube.com/watch?v={item['id']}",
        })
    return {
        "name": name,
        "channel_id": info.get("channel_id"),
        "channel_url": info.get("channel_url") or url,
        "latest": entries,
    }


def main() -> None:
    fetched_at = datetime.now(timezone.utc).isoformat()
    channels, errors = [], []
    for name, url in CHANNELS.items():
        try:
            channels.append(fetch_channel(name, url))
        except Exception as exc:
            errors.append({"name": name, "source": url, "error": str(exc)})

    snapshot = {"fetched_at": fetched_at, "channels": channels, "errors": errors}
    data = Path("data")
    data.mkdir(exist_ok=True)
    (data / "latest.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (data / "history.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
    print(json.dumps({"fetched_at": fetched_at, "channels": len(channels), "errors": len(errors)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
