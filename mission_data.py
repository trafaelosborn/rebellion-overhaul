"""Mission skills and conditional, per-agent rolls. No game assets or writes."""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
import struct


class PlannerError(ValueError):
    """Unsupported data or an unavailable campaign snapshot."""


@dataclass(frozen=True)
class Character:
    id: int
    name: str
    family: int
    diplomacy: int
    espionage: int
    combat: int
    leadership: int
    ship_design: int = 0
    troop_training: int = 0
    facility_design: int = 0
    location: str = "Unknown"
    location_id: int = 0
    status: str = "Awaiting orders"


@dataclass(frozen=True)
class Mission:
    name: str
    table: str | None
    skill: str
    formula: str
    context: tuple[str, ...] = ()


MISSIONS = (
    Mission("Espionage", "ESPIMSTB", "espionage", "Espionage"),
    Mission("Sabotage", "SBTGMSTB", "combined", "(Espionage + Combat) / 2, rounded down"),
    Mission("Diplomacy", "DIPLMSTB", "diplomacy", "Diplomacy - support + Stormtroopers",
            ("support", "stormtroopers")),
    Mission("Recruitment", "RCRTMSTB", "leadership", "Leadership - support (major characters only)",
            ("support",)),
    Mission("Rescue", "RESCMSTB", "combat", "Combat"),
    Mission("Abduction", "ABDCMSTB", "combat", "Combat - target Combat", ("target_combat",)),
    Mission("Assassination", "ASSNMSTB", "combat", "Combat - target Combat", ("target_combat",)),
    Mission("Incite uprising", "INCTMSTB", "leadership", "Leadership - support - Stormtroopers",
            ("support", "stormtroopers")),
    Mission("Subdue uprising", "SUBDMSTB", "leadership", "Leadership - support + Stormtroopers",
            ("support", "stormtroopers")),
    Mission("Death Star sabotage", "DSSBMSTB", "combined", "(Espionage + Combat) / 2, rounded down"),
    Mission("Ship research", None, "ship_design", "Ship Design capability; research uses a separate resolution rule"),
    Mission("Troop research", None, "troop_training", "Troop Training capability; research uses a separate resolution rule"),
    Mission("Facility research", None, "facility_design", "Facility Design capability; research uses a separate resolution rule"),
)
MISSION_BY_NAME = {m.name: m for m in MISSIONS}
TABLE_NAMES = frozenset(m.table for m in MISSIONS if m.table)


@dataclass(frozen=True)
class ProbabilityTable:
    """The original IntTable lookup is a step function, NOT interpolation."""
    rows: tuple[tuple[int, int], ...]

    def __post_init__(self):
        if not self.rows or any(type(x) is not int or type(p) is not int or not 0 <= p <= 100
                                for x, p in self.rows):
            raise PlannerError("Invalid probability table values")
        if any(a[0] >= b[0] for a, b in zip(self.rows, self.rows[1:])):
            raise PlannerError("Probability thresholds must be strictly increasing")

    @classmethod
    def decode(cls, data: bytes) -> ProbabilityTable:
        if len(data) < 25:
            raise PlannerError("Truncated IntTable header")
        version, count, length = struct.unpack_from("<III", data)
        if (version != 1 or not 1 <= count <= 4096 or length != 13
                or data[12:25] != b"IntTableEntry" or len(data) != 25 + count * 16):
            raise PlannerError("Unsupported IntTable format")
        rows = []
        ids = set()
        for offset in range(25, len(data), 16):
            ident, marker, threshold, probability = struct.unpack_from("<IIii", data, offset)
            if marker != 1 or ident in ids:
                raise PlannerError("Invalid IntTable record")
            ids.add(ident)
            rows.append((threshold, probability))
        return cls(tuple(rows))

    def lookup(self, score: int) -> tuple[int, int]:
        index = max(0, bisect_right([r[0] for r in self.rows], score) - 1)
        return self.rows[index]


def load_tables(game: Path) -> dict[str, ProbabilityTable]:
    result = {}
    for name in sorted(TABLE_NAMES):
        try:
            result[name] = ProbabilityTable.decode((game / "GData" / f"{name}.DAT").read_bytes())
        except (OSError, PlannerError) as error:
            raise PlannerError(f"{name}: {error}") from error
    return result


def skill_score(character: Character, mission: Mission) -> int:
    if mission.skill == "combined":
        return (character.espionage + character.combat) // 2
    return getattr(character, mission.skill)


def eligibility(character: Character, mission: Mission) -> str | None:
    if mission.name == "Recruitment" and character.family >= 0x38:
        return "Only major characters can recruit"
    if mission.table is None and skill_score(character, mission) == 0:
        return "No capability for this research"
    return None


@dataclass(frozen=True)
class Roll:
    score: int | None
    threshold: int | None
    percent: int | None
    explanation: str


def evaluate(character: Character, mission: Mission, tables: dict[str, ProbabilityTable],
             context: dict[str, int | None], role: str = "Agent") -> Roll:
    if role == "Decoy":
        return Roll(character.espionage, None, None,
                    "Decoys use Espionage against individual defenders; they do not roll mission success.")
    if reason := eligibility(character, mission):
        return Roll(None, None, None, reason)
    for field in mission.context:
        value = context.get(field)
        if value is None:
            return Roll(None, None, None, f"Enter {field.replace('_', ' ')} from known target information.")
        if type(value) is not int or not 0 <= value <= (100 if field == "support" else 32767):
            raise PlannerError(f"Invalid {field.replace('_', ' ')}")
    score = skill_score(character, mission)
    if "support" in mission.context:
        score -= context["support"]
    if "stormtroopers" in mission.context:
        score += context["stormtroopers"] * (-1 if mission.name == "Incite uprising" else 1)
    if "target_combat" in mission.context:
        score -= context["target_combat"]
    if mission.table is None:
        return Roll(score, None, None, "Research odds are not implemented; this is the current capability.")
    table = tables.get(mission.table)
    if table is None:
        return Roll(score, None, None, "The installed probability table is unavailable.")
    threshold, chance = table.lookup(score)
    return Roll(score, threshold, chance,
                f"{mission.table}: score {score}, threshold {threshold}, roll 0-99 < {chance}. "
                "Per agent, per resolution attempt, conditional on reaching that phase.")


def team_warnings(members: list[Character]) -> list[str]:
    warnings = []
    if len({c.location_id for c in members}) > 1:
        warnings.append("These characters are in different locations; the game may refuse this team.")
    if any(c.status != "Awaiting orders" for c in members):
        warnings.append("Some members are busy, injured, captured, or traveling. Check their in-game availability.")
    return warnings
