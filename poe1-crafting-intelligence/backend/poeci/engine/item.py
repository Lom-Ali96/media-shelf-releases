"""Item state: the thing every crafting action transforms."""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from ..knowledge.gamedata import Base, GameData, Mod

RARITIES = ("normal", "magic", "rare", "unique")
JEWEL_DOMAINS = {"jewel", "abyss_jewel", "affliction_jewel"}


class UnsupportedMechanic(Exception):
    """Raised when an item uses a mechanic the engine does not model yet.

    The engine refuses rather than silently producing wrong probabilities."""


@dataclass(frozen=True)
class ModInstance:
    mod_id: str
    values: tuple[int, ...] = ()
    fractured: bool = False
    crafted: bool = False


@dataclass(frozen=True)
class ItemState:
    base_id: str
    item_level: int
    rarity: str = "normal"
    explicits: tuple[ModInstance, ...] = ()
    influences: frozenset[str] = frozenset()
    corrupted: bool = False
    synthesised: bool = False
    quality: int = 0

    def with_(self, **kw) -> "ItemState":
        return replace(self, **kw)


@dataclass
class ItemView:
    """ItemState joined with game data: convenience accessors used by the rules."""

    gd: GameData
    item: ItemState
    base: Base = field(init=False)

    def __post_init__(self):
        if self.item.base_id not in self.gd.bases:
            raise KeyError(f"unknown base {self.item.base_id}")
        self.base = self.gd.bases[self.item.base_id]

    def mods(self) -> list[tuple[ModInstance, Mod]]:
        return [(mi, self.gd.mods[mi.mod_id]) for mi in self.item.explicits]

    def count(self, gen_type: str) -> int:
        return sum(1 for _, m in self.mods() if m.generation_type == gen_type)

    def max_affixes(self) -> int:
        """Maximum prefixes (= maximum suffixes) for this rarity/base."""
        r = self.item.rarity
        if r == "magic":
            return 1
        if r == "rare":
            return 2 if self.base.domain in JEWEL_DOMAINS else 3
        return 0

    def open_slots(self, gen_type: str) -> int:
        return max(0, self.max_affixes() - self.count(gen_type))

    def groups(self) -> set[str]:
        return {g for _, m in self.mods() for g in m.groups}

    def tags(self) -> set[str]:
        tags = set(self.base.tags)
        for infl in self.item.influences:
            t = self.gd.influence_tag(self.base, infl)
            if t:
                tags.add(t)
        for _, m in self.mods():
            tags.update(m.adds_tags)
        return tags

    # ---- metamods (crafted "item generation" modifiers) ---------------------
    def _has(self, needle: str) -> bool:
        return any(needle in mi.mod_id for mi in self.item.explicits)

    def check_supported(self) -> None:
        for mi in self.item.explicits:
            if "CannotChangeOne" in mi.mod_id or "CannotChangeTwo" in mi.mod_id:
                raise UnsupportedMechanic(
                    f"{mi.mod_id}: partial prefix/suffix locks are not modelled yet (see CRAFTING_COVERAGE.md)"
                )

    @property
    def prefixes_locked(self) -> bool:
        return self._has("CannotChangePrefixes")

    @property
    def suffixes_locked(self) -> bool:
        return self._has("CannotChangeSuffixes")

    @property
    def cannot_roll_attack(self) -> bool:
        return self._has("CannotRollAttackAffixes")

    @property
    def cannot_roll_caster(self) -> bool:
        return self._has("CannotRollCasterAffixes")

    @property
    def multimod(self) -> bool:
        return self._has("CanHaveMultipleCraftedMods")

    def is_protected(self, mi: ModInstance) -> bool:
        """True if a reroll/removal action must leave this mod alone."""
        if mi.fractured:
            return True
        m = self.gd.mods[mi.mod_id]
        if m.generation_type == "prefix" and self.prefixes_locked:
            return True
        if m.generation_type == "suffix" and self.suffixes_locked:
            return True
        return False


def tier_index(gd: GameData, base: Base, mod: Mod, extra_tags: set[str] | None = None) -> tuple[int, int]:
    """(tier, number_of_tiers) for `mod` on `base`; tier 1 is the best.

    Tiers are derived exactly like the in-game advanced item description: all
    mods of the same `type` and affix type that can spawn on this base, ordered
    by required item level (highest first)."""
    tags = frozenset(set(base.tags) | (extra_tags or set()))
    cache = gd.__dict__.setdefault("_tier_cache", {})
    key = (base.id, mod.type, mod.generation_type, tags)
    ids = cache.get(key)
    if ids is None:
        ids = cache[key] = _tier_family(gd, base, mod, tags)
    if mod.id not in ids:
        return (0, len(ids))  # e.g. essence-only or influence mod not in base family
    return (ids.index(mod.id) + 1, len(ids))


def _tier_family(gd: GameData, base: Base, mod: Mod, tags: frozenset[str]) -> list[str]:
    family = [
        m
        for m in gd.affix_mods_by_domain.get(base.domain, [])
        if m.type == mod.type
        and m.generation_type == mod.generation_type
        and not m.is_essence_only
        and spawn_weight(m, tags) > 0
    ]
    family.sort(key=lambda m: (-m.required_level, -(m.stats[0][2] if m.stats else 0)))
    return [m.id for m in family]


def spawn_weight(mod: Mod, tags: set[str]) -> int:
    """First matching tag in the mod's spawn_weights list decides (game rule)."""
    for tag, w in mod.spawn_weights:
        if tag in tags:
            return w
    return 0


def generation_multiplier(mod: Mod, tags: set[str]) -> float:
    """Optional per-item multiplier (percent) applied on top of spawn weight."""
    for tag, w in mod.generation_weights:
        if tag in tags:
            return w / 100.0
    return 1.0
