"""Downloads a versioned snapshot of PoE1 game data from the RePoE export.

Every snapshot lives in its own folder named after the game client version
(e.g. data/snapshots/3.30.0.4.3/) together with a manifest.json recording where
each file came from, when, and its SHA-256. Old snapshots are kept so that
calculations made under an older patch stay reproducible.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .. import config


def fetch_remote_version(client: httpx.Client | None = None) -> str:
    """Game client version that the RePoE export was generated from (e.g. '3.30.0.4.3')."""
    own = client is None
    client = client or httpx.Client(timeout=30, headers={"User-Agent": config.USER_AGENT})
    try:
        r = client.get(f"{config.REPOE_RAW_BASE}/version.txt")
        r.raise_for_status()
        return r.text.strip()
    finally:
        if own:
            client.close()


def snapshot_path(version: str) -> Path:
    return config.SNAPSHOT_DIR / version


def list_snapshots() -> list[str]:
    if not config.SNAPSHOT_DIR.exists():
        return []
    return sorted(
        (p.name for p in config.SNAPSHOT_DIR.iterdir() if (p / "manifest.json").exists()),
        key=_version_key,
    )


def latest_snapshot() -> Path | None:
    snaps = list_snapshots()
    return snapshot_path(snaps[-1]) if snaps else None


def _version_key(v: str) -> tuple:
    return tuple(int(x) if x.isdigit() else x for x in v.replace("-", ".").split("."))


def import_snapshot(force: bool = False, progress=print) -> Path:
    """Download all configured files into a new snapshot folder. Idempotent."""
    with httpx.Client(timeout=300, headers={"User-Agent": config.USER_AGENT}, follow_redirects=True) as client:
        version = fetch_remote_version(client)
        target = snapshot_path(version)
        if (target / "manifest.json").exists() and not force:
            progress(f"Snapshot {version} already present at {target}")
            return target
        tmp = target.with_name(target.name + ".partial")
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True)
        files = {}
        for name in config.REPOE_FILES:
            url = f"{config.REPOE_RAW_BASE}/data/{name}"
            progress(f"Downloading {url}")
            r = client.get(url)
            r.raise_for_status()
            json.loads(r.content)  # refuse to store anything that is not valid JSON
            (tmp / name).write_bytes(r.content)
            files[name] = {"url": url, "sha256": hashlib.sha256(r.content).hexdigest(), "bytes": len(r.content)}
        manifest = {
            "game_version": version,
            "source": "RePoE fork (repoe-fork.github.io), generated from the PoE1 game files",
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "files": files,
        }
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=2))
        if target.exists():
            shutil.rmtree(target)
        tmp.rename(target)
        progress(f"Imported game data {version} -> {target}")
        return target


if __name__ == "__main__":  # python -m poeci.knowledge.importer
    import sys

    import_snapshot(force="--force" in sys.argv)
