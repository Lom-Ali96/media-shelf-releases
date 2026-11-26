"""Parse items copied from the PoE1 client (Ctrl+C and the advanced Ctrl+Alt+C).

The advanced format names each mod and its tier, so it identifies mods with
certainty. The basic format only has the rolled text; mods are matched against
the game data by text + value range, and anything that matches several mods is
reported as ambiguous instead of guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..engine.item import ItemState, ModInstance, spawn_weight, tier_index
from ..knowledge.gamedata import GameData, Mod

SEP = "--------"
INFLUENCE_LINES = {
    "Shaper Item": "shaper",
    "Elder Item": "elder",
    "Crusader Item": "crusader",
    "Hunter Item": "hunter",
    "Redeemer Item": "redeemer",
    "Warlord Item": "warlord",
}
SKIP_PREFIXES = (
    "Requirements", "Level:", "Str:", "Dex:", "Int:", "Sockets:", "Item Level:", "Quality", "Note:",
    "Armour:", "Evasion Rating:", "Energy Shield:", "Ward:", "Chance to Block:", "Physical Damage:",
    "Elemental Damage:", "Critical Strike Chance:", "Attacks per Second:", "Weapon Range:",
    "Stack Size:", "Limited to:", "Radius:", "Searing Exarch Item", "Eater of Worlds Item",
    "Unidentified", "Mirrored", "Split", "Corrupted", "Synthesised Item", "Fractured Item",
    "Recovers", "Consumes", "Currently has",
)
ADV_HEADER = re.compile(
    r'^\{ (?P<kind>(?:Fractured |Master Crafted |Crafted |Essence )?(?:Prefix|Suffix)) Modifier'
    r'(?: "(?P<name>[^"]*)")?(?: \((?:Tier|Rank): (?P<tier>\d+)\))?'
)
ADV_OTHER_HEADER = re.compile(r"^\{ (Implicit|Unique|Enchant|Searing Exarch|Eater of Worlds|Corruption)")
RANGE_AFTER_VALUE = re.compile(r"(?<=\d)\((-?[\d.]+)-(-?[\d.]+)\)")
NUM = r"(-?\d+(?:\.\d+)?)"


@dataclass
class ParsedMod:
    lines: list[str]
    kind: str  # prefix / suffix / unknown
    crafted: bool = False
    fractured: bool = False
    candidates: list[str] = field(default_factory=list)
    mod_id: str | None = None
    tier: int | None = None
    values: list[float] = field(default_factory=list)
    status: str = "unmatched"  # matched / ambiguous / unmatched


@dataclass
class ParsedItem:
    item_class: str = ""
    rarity: str = ""
    name: str = ""
    base_name: str = ""
    base_id: str | None = None
    item_level: int | None = None
    influences: list[str] = field(default_factory=list)
    corrupted: bool = False
    synthesised: bool = False
    implicits: list[str] = field(default_factory=list)
    enchants: list[str] = field(default_factory=list)
    mods: list[ParsedMod] = field(default_factory=list)
    advanced_format: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_item_state(self) -> ItemState | None:
        if not self.base_id or self.item_level is None:
            return None
        if any(m.status != "matched" for m in self.mods):
            return None
        return ItemState(
            base_id=self.base_id,
            item_level=self.item_level,
            rarity=self.rarity.lower(),
            explicits=tuple(
                ModInstance(m.mod_id, tuple(int(round(v)) for v in m.values), m.fractured, m.crafted) for m in self.mods
            ),
            influences=frozenset(self.influences),
            corrupted=self.corrupted,
            synthesised=self.synthesised,
        )


# ------------------------------------------------------------------ helpers
def _template_regex(line: str) -> re.Pattern:
    """'+(100-114) to maximum Life' -> ^\\+(num) to maximum Life$"""
    out, pos = [], 0
    for m in re.finditer(r"\((-?[\d.]+)-(-?[\d.]+)\)", line):
        out.append(re.escape(line[pos:m.start()]))
        out.append(NUM)
        pos = m.end()
    out.append(re.escape(line[pos:]))
    return re.compile("^" + "".join(out) + "$", re.IGNORECASE)


def _text_ranges(line: str) -> list[tuple[float, float]]:
    return [(float(a), float(b)) for a, b in re.findall(r"\((-?[\d.]+)-(-?[\d.]+)\)", line)]


def _match_lines(mod: Mod, lines: list[str]) -> list[float] | None:
    """Values if `lines` render `mod`, checking each value lies in the mod's range."""
    tlines = mod.text.split("\n")
    if len(tlines) != len(lines):
        return None
    values: list[float] = []
    for tl, line in zip(tlines, lines):
        m = _template_regex(tl).match(line)
        if not m:
            return None
        got = [float(g) for g in m.groups()]
        for v, (lo, hi) in zip(got, _text_ranges(tl)):
            lo, hi = min(lo, hi), max(lo, hi)
            if not (lo <= v <= hi):
                return None
        values.extend(got)
    return values


def _clean_line(line: str) -> tuple[str, str | None]:
    for suffix in ("implicit", "crafted", "fractured", "enchant"):
        tag = f" ({suffix})"
        if line.endswith(tag):
            return line[: -len(tag)], suffix
    return line, None


class ItemParser:
    def __init__(self, gd: GameData):
        self.gd = gd

    def _base_from_names(self, rarity: str, names: list[str]) -> str:
        if rarity in ("Rare", "Unique") and len(names) >= 2:
            return names[1]
        line = names[0] if names else ""
        if line in self.gd.bases_by_name:
            return line
        # Magic: "Hale Sapphire Ring of the Inuit" -> longest base name contained
        best = ""
        for name in self.gd.bases_by_name:
            if name and name in line and len(name) > len(best):
                best = name
        return best

    def _candidate_mods(self, item: ParsedItem, crafted: bool) -> list[Mod]:
        base = self.gd.bases.get(item.base_id or "")
        if base is None:
            return []
        if crafted:
            bench = {
                (o.get("actions") or {}).get("add_explicit_mod")
                for o in self.gd.bench_options
                if base.item_class in (o.get("item_classes") or ())
            }
            on_bench = [self.gd.mods[i] for i in bench if i in self.gd.mods]
            # fall back to every crafted mod (e.g. legacy crafts) only if nothing on the bench fits
            return on_bench or [m for m in self.gd.mods.values() if m.domain == "crafted" and m.is_affix]
        tags = set(base.tags) | {t for i in item.influences if (t := self.gd.influence_tag(base, i))}
        essence_mods = {
            mid for _, e in self.gd.essences.items() if (mid := (e.get("mods") or {}).get(base.item_class))
        }
        return [
            m
            for m in self.gd.affix_mods_by_domain.get(base.domain, [])
            if ((m.id in essence_mods) if m.is_essence_only else spawn_weight(m, tags) > 0)
        ]

    def parse(self, text: str) -> ParsedItem:
        text = text.replace("\r\n", "\n").strip()
        sections = [[ln.strip() for ln in s.strip().split("\n") if ln.strip()] for s in text.split(SEP)]
        item = ParsedItem()
        if not sections or not sections[0]:
            item.warnings.append("empty input")
            return item
        header = sections[0]
        names = []
        for ln in header:
            if ln.startswith("Item Class:"):
                item.item_class = ln.split(":", 1)[1].strip()
            elif ln.startswith("Rarity:"):
                item.rarity = ln.split(":", 1)[1].strip()
            else:
                names.append(ln)
        item.name = names[0] if names else ""
        item.base_name = self._base_from_names(item.rarity, names)
        base = self.gd.bases_by_name.get(item.base_name)
        if base:
            item.base_id = base.id
        else:
            item.warnings.append(f"could not identify base type from {names!r}")
        if item.rarity == "Unique":
            item.warnings.append("unique items are not analysed yet; only base/item level are reported")

        item.advanced_format = any(ln.startswith("{ ") for s in sections for ln in s)
        pending: ParsedMod | None = None
        for sec in sections[1:]:
            mode = None  # for advanced format: which header we are under
            for raw in sec:
                if raw.startswith("Item Level:"):
                    item.item_level = int(raw.split(":", 1)[1].strip())
                    continue
                if raw in INFLUENCE_LINES:
                    item.influences.append(INFLUENCE_LINES[raw])
                    continue
                if raw == "Corrupted":
                    item.corrupted = True
                    continue
                if raw == "Synthesised Item":
                    item.synthesised = True
                    continue
                if item.advanced_format and raw.startswith("{"):
                    h = ADV_HEADER.match(raw)
                    if h:
                        kind = h.group("kind")
                        pending = ParsedMod(
                            lines=[],
                            kind="prefix" if "Prefix" in kind else "suffix",
                            crafted="Crafted" in kind,
                            fractured="Fractured" in kind,
                        )
                        pending.candidates = [h.group("name") or ""]
                        pending.tier = int(h.group("tier")) if h.group("tier") else None
                        item.mods.append(pending)
                        mode = "mod"
                    elif ADV_OTHER_HEADER.match(raw):
                        mode = "implicit" if "Implicit" in raw else "other"
                        pending = None
                    continue
                if raw.startswith(SKIP_PREFIXES) or raw.endswith(" Item"):
                    continue
                line, tag = _clean_line(raw)
                line = RANGE_AFTER_VALUE.sub("", line)
                if item.advanced_format:
                    if mode == "mod" and pending is not None:
                        if line.startswith("(") and line.endswith(")"):
                            continue  # reminder text
                        pending.lines.append(line)
                    elif mode == "implicit":
                        item.implicits.append(line)
                    continue
                # basic format
                if tag == "implicit":
                    item.implicits.append(line)
                elif tag == "enchant":
                    item.enchants.append(line)
                elif item.item_level is not None and not (line.startswith("(") and line.endswith(")")):
                    item.mods.append(ParsedMod(lines=[line], kind="unknown", crafted=tag == "crafted", fractured=tag == "fractured"))
        if item.item_level is None:
            item.warnings.append("no 'Item Level' line found")
        if item.base_id:
            if item.advanced_format:
                self._resolve_advanced(item)
            else:
                self._resolve_basic(item)
        return item

    # --------------------------------------------------------- resolution
    def _resolve_advanced(self, item: ParsedItem) -> None:
        base = self.gd.bases[item.base_id]
        tags = set(base.tags) | {t for i in item.influences if (t := self.gd.influence_tag(base, i))}
        for pm in item.mods:
            name = pm.candidates[0] if pm.candidates else ""
            pool = [m for m in self._candidate_mods(item, pm.crafted) if m.generation_type == pm.kind]
            hits = []
            for m in pool:
                if not pm.crafted and m.name != name:
                    continue
                vals = _match_lines(m, pm.lines)
                if vals is None:
                    continue
                if not pm.crafted and pm.tier is not None and tier_index(self.gd, base, m, tags)[0] not in (0, pm.tier):
                    continue
                hits.append((m, vals))
            self._settle(pm, hits)

    def _resolve_basic(self, item: ParsedItem) -> None:
        # Try to pair consecutive lines into hybrid mods first, then single lines.
        resolved: list[ParsedMod] = []
        i = 0
        mods = item.mods
        while i < len(mods):
            pm = mods[i]
            if i + 1 < len(mods) and mods[i + 1].crafted == pm.crafted and mods[i + 1].fractured == pm.fractured:
                a, b = pm.lines[0], mods[i + 1].lines[0]
                for pair in ([a, b], [b, a]):  # Path of Building lists hybrid lines in its own order
                    hits = [(m, v) for m in self._candidate_mods(item, pm.crafted) if "\n" in m.text and (v := _match_lines(m, pair)) is not None]
                    if hits:
                        break
                if hits:
                    merged = ParsedMod(lines=pair, kind="unknown", crafted=pm.crafted, fractured=pm.fractured)
                    self._settle(merged, hits)
                    resolved.append(merged)
                    i += 2
                    continue
            hits = [(m, v) for m in self._candidate_mods(item, pm.crafted) if (v := _match_lines(m, pm.lines)) is not None]
            self._settle(pm, hits)
            resolved.append(pm)
            i += 1
        item.mods = resolved
        if any(m.status == "ambiguous" for m in item.mods):
            item.warnings.append(
                "some modifiers match several possible mods (e.g. a hybrid or a value inside two tier ranges); "
                "copy the item with Ctrl+Alt+C for exact identification"
            )

    def _settle(self, pm: ParsedMod, hits: list[tuple[Mod, list[float]]]) -> None:
        # Distinct mod ids with identical text, ranges and affix type (e.g. the same
        # bench craft listed under several masters) are the same mod for our purposes.
        uniq: dict[tuple, tuple[Mod, list[float]]] = {}
        for m, v in hits:
            uniq.setdefault((m.text, m.generation_type, m.groups), (m, v))
        hits = list(uniq.values())
        pm.candidates = [m.id for m, _ in hits]
        if len(hits) == 1:
            m, vals = hits[0]
            pm.mod_id, pm.values, pm.kind, pm.status = m.id, vals, m.generation_type, "matched"
        elif len(hits) > 1:
            pm.status = "ambiguous"
        else:
            pm.status = "unmatched"
