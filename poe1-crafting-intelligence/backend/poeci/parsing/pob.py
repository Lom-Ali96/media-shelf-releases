"""Import items from a Path of Building code (also what poe.ninja character pages export).

A PoB code is url-safe base64 of zlib-compressed XML. Each <Item> holds PoB's
item text, which is converted here into the game's basic Ctrl+C format so the
normal clipboard parser identifies the mods (basic format: no tiers in the
text, so mods are matched by value and ambiguity is reported, never guessed).
Format checked against a PoB Community build saved on 2026-11-26.
"""
from __future__ import annotations

import base64
import re
import zlib
import xml.etree.ElementTree as ET

from .clipboard import INFLUENCE_LINES, SEP

MAX_XML_BYTES = 20_000_000  # a real build is well under 1 MB
ASSUMED_ITEM_LEVEL = 86  # shown as an assumption: PoB-made items carry no item level
_TAG = re.compile(r"\{(\w+)(?::([^}]*))?\}")
_RANGE = re.compile(r"\((-?[\d.]+)-(-?[\d.]+)\)")


class PobError(Exception):
    pass


def decode(code: str) -> str:
    code = "".join(code.split())
    if code.startswith("http"):
        raise PobError("that is a link: open it and copy the Path of Building code shown there")
    try:
        raw = base64.urlsafe_b64decode(code.replace("+", "-").replace("/", "_") + "=" * (-len(code) % 4))
        d = zlib.decompressobj()
        xml = d.decompress(raw, MAX_XML_BYTES)
        if d.unconsumed_tail:
            raise PobError("build is too large")
    except PobError:
        raise
    except Exception as e:  # noqa: BLE001 - any decoding failure means "not a PoB code"
        raise PobError("this is not a Path of Building code") from e
    return xml.decode("utf-8", "replace")


def _resolve_line(line: str) -> tuple[str, set[str]]:
    """Strip PoB {tags}; turn '(a-b)' ranges into the rolled value via {range:x}."""
    tags, r = set(), None
    while (m := _TAG.match(line)):
        tags.add(m.group(1))
        if m.group(1) == "range":
            r = float(m.group(2))
        line = line[m.end():]
    if r is not None:
        def roll(m):
            lo, hi = float(m.group(1)), float(m.group(2))
            v = lo + (hi - lo) * r
            return f"{v:g}" if "." in m.group(0) else str(int(round(v)))
        line = _RANGE.sub(roll, line)
    return line, tags


def to_clipboard(pob_text: str) -> str:
    """PoB item text -> game Ctrl+C (basic) text."""
    lines = [ln.strip() for ln in pob_text.strip().splitlines() if ln.strip()]
    if not lines or not lines[0].startswith("Rarity:"):
        raise PobError("item text has no Rarity line")
    rarity = lines[0].split(":", 1)[1].strip().title()
    names, i = [], 1
    while i < len(lines) and len(names) < (1 if rarity in ("Normal", "Magic") else 2) and ":" not in lines[i]:
        names.append(lines[i])
        i += 1
    ilvl, influences, implicits, mods = None, [], [], []
    n_implicit = None
    for ln in lines[i:]:
        if n_implicit is None:
            if ln.startswith("Item Level:"):
                ilvl = ln.split(":", 1)[1].strip()
            elif ln in INFLUENCE_LINES:
                influences.append(ln)
            elif ln.startswith("Implicits:"):
                n_implicit = int(ln.split(":", 1)[1])
            continue  # other PoB header lines (Unique ID, Sockets, Prefix: ..., Variant ...)
        text, tags = _resolve_line(ln)
        if "variant" in tags:
            continue  # variant lines need PoB's variant selection; not modelled
        suffix = " (crafted)" if "crafted" in tags else " (fractured)" if "fractured" in tags else ""
        if len(implicits) < n_implicit:
            implicits.append(text + " (implicit)")
        else:
            mods.append(text + suffix)
    sections = [[f"Rarity: {rarity}", *names]]
    # Items made inside PoB have no item level; the parser needs one to read mods.
    sections.append([f"Item Level: {ilvl or ASSUMED_ITEM_LEVEL}"])
    for block in (implicits, mods, influences):
        if block:
            sections.append(block)
    return f"\n{SEP}\n".join("\n".join(s) for s in sections) + "\n"


def items(code: str) -> list[dict]:
    """Equipped items of the active item set (slot, PoB text, Ctrl+C text)."""
    try:
        root = ET.fromstring(decode(code))
    except ET.ParseError as e:
        raise PobError("the code decodes, but the build data is broken") from e
    node = root.find("Items")
    if node is None:
        raise PobError("no items in this build")
    by_id = {it.get("id"): (it.text or "") for it in node.findall("Item")}
    sets = {s.get("id"): s for s in node.findall("ItemSet")}
    active = sets.get(node.get("activeItemSet"))
    if active is None:  # explicit check: an Element with no children is falsy
        active = next(iter(sets.values()), node)
    out, seen = [], set()
    for slot in active.findall("Slot"):
        iid = slot.get("itemId")
        if iid in (None, "0") or iid not in by_id or iid in seen:
            continue
        seen.add(iid)
        text = by_id[iid]
        entry = {"slot": slot.get("name"), "pob_text": text.strip(), "item_level_assumed": "Item Level:" not in text}
        try:
            entry["text"] = to_clipboard(text)
        except PobError as e:
            entry["error"] = str(e)
        out.append(entry)
    return out
