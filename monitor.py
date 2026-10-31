from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

CHANNELS = {
    "Zentric Minecraft": "UCBoZcTLayAUgYTPsyrStiLg",
    "Klorna": "@Klorna1",
    "Jocuri Horror": "@JocuriHorrorSky",
    "Valeriu Coadă": "@valeriucoada",
}

NS = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "zentric-youtube-monitor/1.0"})
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read()


def resolve_channel_id(handle: str) -> str:
    if handle.startswith("UC"):
        return handle
    html = get("https://www.youtube.com/" + handle)
    match = re.search(rb'"channelId":"(UC[^"]+)"', html)
    if not match:
        raise RuntimeError(f"channel id not found for {handle}")
    return match.group(1).decode()


def fetch_feed(channel_id: str) -> list[dict]:
    root = ET.fromstring(get("https://www.youtube.com/feeds/videos.xml?channel_id=" + urllib.parse.quote(channel_id)))
    rows = []
    for entry in root.findall("atom:entry", NS):
        video_id = entry.findtext("yt:videoId", namespaces=NS)
        title = entry.findtext("atom:title", namespaces=NS)
        published = entry.findtext("atom:published", namespaces=NS)
        updated = entry.findtext("atom:updated", namespaces=NS)
        link = next((x.attrib.get("href") for x in entry.findall("atom:link", NS) if x.attrib.get("rel") == "alternate"), None)
        rows.append({"video_id": video_id, "title": title, "published": published, "updated": updated, "url": link})
    return rows


def main() -> None:
    fetched_at = datetime.now(timezone.utc).isoformat()
    channels, errors = [], []
    for name, ref in CHANNELS.items():
        try:
            channel_id = resolve_channel_id(ref)
            videos = fetch_feed(channel_id)
            channels.append({"name": name, "channel_id": channel_id, "source": ref, "latest": videos[:15]})
            time.sleep(0.5)
        except Exception as exc:
            errors.append({"name": name, "source": ref, "error": str(exc)})

    snapshot = {"fetched_at": fetched_at, "channels": channels, "errors": errors}
    data = Path("data")
    data.mkdir(exist_ok=True)
    (data / "latest.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (data / "history.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
    print(json.dumps({"fetched_at": fetched_at, "channels": len(channels), "errors": len(errors)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
