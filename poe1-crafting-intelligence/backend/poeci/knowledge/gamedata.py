"""Read-only, indexed view over one game-data snapshot.

This module only *describes* the game data. Rules about how crafting actions use
it live in poeci.engine.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

# Domains whose bases can roll random prefixes/suffixes. A base only rolls mods of
# its own domain (rings/armour/weapons = "item", flasks = "flask", ...).
CRAFTABLE_DOMAINS = {"item", "flask", "jewel", "abyss_jewel", "affliction_jewel"}

# Influence name as shown on items -> suffix used in the item-class influence tags
# (item_classes.json lists e.g. "ring_basilisk" for Hunter).
INFLUENCE_TAG_SUFFIX = {
    "shaper": "shaper",
    "elder": "elder",
    "crusader": "crusader",
    "hunter": "basilisk",
    "redeemer": "eyrie",
    "warlord": "adjudicator",
}


_MARKUP = re.compile(r"\[([^\]|]+)\|([^\]]+)\]|\[([^\]]+)\]")


def clean_text(text: str) -> str:
    """Strip in-game link markup: '[PlayerItemRarity|Item Rarity]' -> 'Item Rarity'."""
    return _MARKUP.sub(lambda m: m.group(2) or m.group(3), text)


@dataclass(frozen=True)
class Mod:
    id: str
    name: str
    domain: str
    generation_type: str
    type: str
    groups: tuple[str, ...]
    required_level: int
    spawn_weights: tuple[tuple[str, int], ...]
    generation_weights: tuple[tuple[str, int], ...]
    implicit_tags: tuple[str, ...]
    adds_tags: tuple[str, ...]
    is_essence_only: bool
    text: str
    stats: tuple[tuple[str, int, int], ...]  # (stat id, min, max)

    @property
    def is_affix(self) -> bool:
        return self.generation_type in ("prefix", "suffix")

    @classmethod
    def from_json(cls, mod_id: str, d: dict) -> "Mod":
        return cls(
            id=mod_id,
            name=d.get("name") or "",
            domain=d.get("domain") or "",
            generation_type=d.get("generation_type") or "",
            type=d.get("type") or "",
            groups=tuple(d.get("groups") or ()),
            required_level=int(d.get("required_level") or 0),
            spawn_weights=tuple((w["tag"], int(w["weight"])) for w in d.get("spawn_weights") or ()),
            generation_weights=tuple((w["tag"], int(w["weight"])) for w in d.get("generation_weights") or ()),
            implicit_tags=tuple(d.get("implicit_tags") or ()),
            adds_tags=tuple(d.get("adds_tags") or ()),
            is_essence_only=bool(d.get("is_essence_only")),
            text=clean_text(d.get("text") or ""),
            stats=tuple((s["id"], int(s["min"]), int(s["max"])) for s in d.get("stats") or ()),
        )


@dataclass(frozen=True)
class Base:
    id: str
    name: str
    item_class: str
    domain: str
    tags: tuple[str, ...]
    implicits: tuple[str, ...]
    drop_level: int
    release_state: str
    attack_time_ms: int | None = None  # weapons only

    @property
    def craftable(self) -> bool:
        return self.domain in CRAFTABLE_DOMAINS and self.release_state == "released"


class GameData:
    def __init__(self, raw: dict[str, object], manifest: dict):
        self.manifest = manifest
        self.version: str = manifest.get("game_version", "unknown")
        self.mods: dict[str, Mod] = {k: Mod.from_json(k, v) for k, v in raw["mods.json"].items()}
        self.bases: dict[str, Base] = {
            k: Base(
                id=k,
                name=v.get("name") or "",
                item_class=v.get("item_class") or "",
                domain=v.get("domain") or "",
                tags=tuple(v.get("tags") or ()),
                implicits=tuple(v.get("implicits") or ()),
                drop_level=int(v.get("drop_level") or 0),
                release_state=v.get("release_state") or "",
                attack_time_ms=(v.get("properties") or {}).get("attack_time"),
            )
            for k, v in raw["base_items.json"].items()
        }
        self.item_classes: dict = raw.get("item_classes.json", {})
        self.essences: dict = raw.get("essences.json", {})
        self.fossils: dict = raw.get("fossils.json", {})
        self.bench_options: list = raw.get("crafting_bench_options.json", [])

    # ---------------------------------------------------------------- loading
    @classmethod
    def from_dir(cls, path: str | Path) -> "GameData":
        path = Path(path)
        manifest = json.loads((path / "manifest.json").read_text()) if (path / "manifest.json").exists() else {}
        raw = {}
        for f in path.glob("*.json"):
            if f.name != "manifest.json":
                raw[f.name] = json.loads(f.read_text(encoding="utf-8"))
        return cls(raw, manifest)

    # ---------------------------------------------------------------- indexes
    @cached_property
    def craftable_bases(self) -> list[Base]:
        return sorted((b for b in self.bases.values() if b.craftable), key=lambda b: (b.item_class, b.name))

    @cached_property
    def bases_by_name(self) -> dict[str, Base]:
        # Several internal ids can share a name (e.g. legacy duplicates); prefer released ones.
        out: dict[str, Base] = {}
        for b in sorted(self.bases.values(), key=lambda b: b.release_state != "released"):
            out.setdefault(b.name, b)
        return out

    @cached_property
    def affix_mods_by_domain(self) -> dict[str, list[Mod]]:
        out: dict[str, list[Mod]] = {}
        for m in self.mods.values():
            # Royale event-mode mods keep normal spawn weights in the data, but poedb lists them
            # separately as "Royale Modifiers"; they do not roll on normal items (TODO.md, 2026-11-26).
            if m.is_affix and "Royale" not in m.id:
                out.setdefault(m.domain, []).append(m)
        return out

    @cached_property
    def essences_by_name(self) -> dict[str, tuple[str, dict]]:
        return {v["name"]: (k, v) for k, v in self.essences.items()}

    @cached_property
    def fossils_by_name(self) -> dict[str, tuple[str, dict]]:
        return {v["name"]: (k, v) for k, v in self.fossils.items()}

    def influence_tag(self, base: Base, influence: str) -> str | None:
        suffix = INFLUENCE_TAG_SUFFIX.get(influence.lower())
        if not suffix:
            return None
        for tag in self.item_classes.get(base.item_class, {}).get("influence_tags") or ():
            if tag.endswith("_" + suffix):
                return tag
        return None

    def search_bases(self, q: str, limit: int = 50) -> list[Base]:
        q = q.lower().strip()
        hits = [b for b in self.craftable_bases if q in b.name.lower() or q in b.item_class.lower()]
        return hits[:limit]

    def search_mods(self, q: str, limit: int = 100) -> list[Mod]:
        q = q.lower().strip()
        hits = [m for m in self.mods.values() if m.is_affix and (q in m.text.lower() or q in m.name.lower() or q in m.id.lower())]
        return hits[:limit]

    def summary(self) -> dict:
        return {
            "game_version": self.version,
            "mods_total": len(self.mods),
            "affix_mods": sum(1 for m in self.mods.values() if m.is_affix),
            "bases_total": len(self.bases),
            "craftable_bases": len(self.craftable_bases),
            "essences": len(self.essences),
            "fossils": len(self.fossils),
            "bench_options": len(self.bench_options),
            "imported_at": self.manifest.get("imported_at"),
        }
