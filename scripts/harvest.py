#!/usr/bin/env python3
"""
Source harvester.

Fetches every source in sources/sources.yaml and stores a dated plain-text
snapshot under sources/snapshots/<id>/<YYYY-MM-DD>.txt. If a previous
snapshot exists and the content differs, prints a CHANGE alert (this is the
seed of the phase-2 change watcher).

Run from repo root:  python3 scripts/harvest.py [source_id ...]
(no args = harvest everything with a URL)

NOTE: run this from a machine with normal internet access (riksdagen.se,
skatteverket.se etc.). Requires: pip install requests beautifulsoup4 pyyaml
"""

import datetime as dt
import hashlib
import pathlib
import sys

import requests
import yaml
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "sources" / "sources.yaml"
SNAPSHOTS = ROOT / "sources" / "snapshots"

UA = {"User-Agent": "Example Studio-handbook-harvester/1.0 (internal HR documentation)"}


def extract_text(html: str | bytes) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    lines = [ln.strip() for ln in soup.get_text("\n").splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    # Some authority sites serve these error pages with HTTP 200. Never let
    # them become the latest source text used for drafting.
    if text.lower().startswith(("request rejected", "access denied")):
        raise ValueError("source returned an access-denial page, not usable text")
    return text


def latest_snapshot(folder: pathlib.Path):
    if not folder.exists():
        return None
    snaps = sorted(folder.glob("*.txt"))
    return snaps[-1] if snaps else None


def main():
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["sources"]
    wanted = sys.argv[1:] or [k for k, v in registry.items() if v.get("url")]
    today = dt.date.today().isoformat()
    changes = []

    for sid in wanted:
        src = registry.get(sid)
        if src is None:
            print(f"  ✗ {sid}: not in sources.yaml"); continue
        if not src.get("url"):
            print(f"  – {sid}: no URL (manual source, e.g. CBA PDF) — skipped")
            continue

        try:
            resp = requests.get(src["url"], headers=UA, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  ✗ {sid}: fetch failed — {e}"); continue

        # Let BeautifulSoup read the HTML's encoding declaration. Requests can
        # default to Latin-1 for UTF-8 pages whose HTTP header omits a charset.
        try:
            text = extract_text(resp.content)
        except ValueError as e:
            print(f"  ✗ {sid}: extraction failed — {e}"); continue
        folder = SNAPSHOTS / sid
        folder.mkdir(parents=True, exist_ok=True)

        prev = latest_snapshot(folder)
        new_hash = hashlib.sha256(text.encode()).hexdigest()
        if prev is not None:
            old_text = prev.read_text(encoding="utf-8")
            if old_text.startswith("# SNAPSHOT — "):
                old_text = old_text.split("\n\n", 1)[1]
            old_hash = hashlib.sha256(old_text.encode()).hexdigest()
            if old_hash == new_hash:
                print(f"  = {sid}: unchanged since {prev.stem}")
                continue
            changes.append((sid, prev.stem))

        out = folder / f"{today}.txt"
        header = (f"# SNAPSHOT — {src['title']}\n# Source: {src['url']}\n"
                  f"# Fetched: {today}\n# SHA256: {new_hash}\n\n")
        out.write_text(header + text, encoding="utf-8")
        print(f"  ✓ {sid}: snapshot saved → {out.relative_to(ROOT)}")

    if changes:
        print("\n🔔 CONTENT CHANGED since last snapshot — review affected articles:")
        for sid, prev_date in changes:
            print(f"  • {sid} (previous snapshot: {prev_date})")
            print(f"    Find affected articles:  grep -rl '{sid}' content/")
        sys.exit(2)  # non-zero so CI/cron can alert on changes


if __name__ == "__main__":
    main()
