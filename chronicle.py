"""Dynasties & Chronicle (SPEC_DYNASTIES.md D1-D5).

House identity, the salience-scored chronicle, and epithet derivation.
Plain stdlib + no heavy deps: everything here pickles with the sim.

Purpose: turn the terrarium's event stream into HISTORY - named houses
whose deeds are remembered, judged (epithets), and narrated (saga).
Preconditions: callers pass the shared `random` module's stream (the
sim's determinism contract). Failure modes: none fatal - name collisions
are broken with generation numerals; unknown deeds fall back to the
founder epithet.
"""

import random
from typing import Dict, List, Optional, Tuple

# D1: syllable grammar - harsh desert-court phonology, two-part names
_ONSETS = ["V", "K", "Z", "R", "M", "S", "T", "N", "D", "G", "Kh", "Th",
           "Vr", "Sz", "Dr"]
_VOWELS = ["a", "e", "i", "o", "u", "ai", "au", "ei"]
_CODAS = ["x", "rn", "l", "k", "sh", "th", "m", "r", "s", "n", "d", "zz"]

ROW_CAP = 800            # chronicle rows kept after pruning (D4)
PRUNE_KEEP_SALIENCE = 7  # rows at/above this salience are never pruned

# D4: salience of a chronicle row, by event-text substring (first match
# wins; the table is ordered most-specific first)
SALIENCE = [
    ("has fallen", 10),
    ("betrays", 9),
    ("blood feud", 9),
    ("coaxes the ancient machine", 8),
    ("reverse-engineered", 8),
    ("falls silent", 8),
    ("will be remembered", 8),
    ("rises (", 8),
    ("four houses wake", 6),
    ("declares war", 7),
    ("is slain", 7),
    ("besieges", 6),
    ("truce", 6),
    ("coalition", 6),
    ("Wildfire", 6),
    ("puts", 6),           # "...to the torch!"
    ("ram smashes", 6),
    ("catapult hurls", 7),
    ("too strange", 8),
    ("SPEAKS", 10),
    ("no longer a wall", 10),
    ("turns on its god", 10),
    ("Shade stage", 10),
    ("split open", 9),
    ("worship", 8),
    ("augments its mind", 8),
    ("hateful", 8),
    ("castle", 8),
    ("god-brain", 8),
    ("probing the glass", 8),
    ("pads across", 7),
    ("grieving", 7),
    ("withholds", 6),
    ("keeper's hand", 5),
    ("computes its fortunes", 6),
    ("mints", 5),
    ("gift", 5),
    ("incursion", 5),
    ("flash flood", 6),
    ("deluge over the sands", 6),
    ("blistering heat", 5),
    ("biting cold", 5),
    ("lights a firecracker", 5),
    ("rain waters the sands", 4),
    ("scatters seeds", 4),
    ("Hail", 4),
    ("frost settles", 4),
    ("floodwaters", 3),
    ("dream", 3),
    ("strikes", 5),        # ore strikes
    ("tribute", 5),
    ("first harvest", 5),
    ("fells its first palm", 4),
    ("raises palisades", 4),
    ("frost takes", 4),
    ("Lightning", 4),
    ("arrived", 4),
    ("sandstorm", 2),
    ("season begins", 2),
    ("Keeper", 1),
]

# D2: deed classes scanned over a reign's rows -> earned epithet.
# (needle, epithet, weight): score = occurrences * weight, so one
# betrayal (5) brands a house harder than two harvests (2 each);
# precedence order breaks exact ties.
EPITHET_RULES = [
    ("betrays", "the Oath-Broken", 5),
    ("coaxes the ancient machine", "the Machine-Waker", 4),
    ("reverse-engineered", "the Machine-Waker", 4),
    ("is slain", "the Beast-Slayer", 3),
    ("puts", "the Burned", 3),        # torched or was torched: fire marks
    ("Wildfire", "the Burned", 3),
    ("ram smashes", "the Wall-Breaker", 3),
    ("truce", "the Oath-Keeper", 2),
    ("tribute", "the Open-Handed", 2),
    ("harvest", "the Farmer-King", 2),
    ("strikes", "the Delver", 2),
    ("raises palisades", "the Stone-Hearted", 2),
    ("declares war", "the Warlord", 1),
    ("besieges", "the Warlord", 1),
]
FOUNDER_EPITHET = "the Founder"


def make_house_name() -> str:
    """One two-part house name from the shared random stream (D1)."""
    def part() -> str:
        return (random.choice(_ONSETS) + random.choice(_VOWELS)
                + random.choice(_CODAS)).capitalize()
    return f"{part()}-{part()}"


ROMAN = ("", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")


def house_label(house: str, generation: int = 1,
                epithet: str = "") -> str:
    """Display form: 'Vex-Karn II, the Oath-Broken' (D1/D2)."""
    numeral = ROMAN[generation] if 0 < generation < len(ROMAN) \
        else str(generation)
    label = house if generation <= 1 else f"{house} {numeral}"
    return f"{label}, {epithet}" if epithet else label


def salience_of(text: str) -> int:
    """Score a chronicle row by the D4 table (default 1)."""
    for needle, score in SALIENCE:
        if needle in text:
            return score
    return 1


def prune(rows: List[Tuple[int, str, int]]) -> List[Tuple[int, str, int]]:
    """Cap the chronicle: drop the lowest-salience, oldest rows first,
    never touching rows at/above PRUNE_KEEP_SALIENCE (D4)."""
    if len(rows) <= ROW_CAP:
        return rows
    excess = len(rows) - ROW_CAP
    keep: List[Tuple[int, str, int]] = []
    # walk salience bands upward, dropping oldest-first inside each band
    droppable = sorted(
        (i for i, r in enumerate(rows) if r[2] < PRUNE_KEEP_SALIENCE),
        key=lambda i: (rows[i][2], rows[i][0]))
    dropped = set(droppable[:excess])
    keep = [r for i, r in enumerate(rows) if i not in dropped]
    return keep[-ROW_CAP:]  # hard cap even if everything was salient


def derive_epithet(rows: List[Tuple[int, str, int]], house: str,
                   founded_step: int) -> str:
    """D2: judge a reign - the dominant deed class of the dead maw's rows.

    Scans rows mentioning `House {house}` from founded_step on (chronicle
    rows are house-substituted at write time); the highest weighted deed
    score wins, precedence order breaking ties. A reign with no notable
    deeds earns FOUNDER_EPITHET.
    """
    tag = f"House {house}"
    reign = [text for step, text, _s in rows
             if step >= founded_step and tag in text]
    best, best_score = FOUNDER_EPITHET, 0
    for needle, epithet, weight in EPITHET_RULES:
        score = weight * sum(1 for text in reign if needle in text)
        if score > best_score:
            best, best_score = epithet, score
    return best


def saga_rows(rows: List[Tuple[int, str, int]], min_salience: int = 4,
              limit: int = 40) -> List[Tuple[int, str, int]]:
    """D5: the readable-history selection - most recent `limit` rows at
    or above `min_salience`, in chronological order."""
    picked = [r for r in rows if r[2] >= min_salience]
    return picked[-limit:]


def write_saga(sim, path: str) -> int:
    """D11: export the full chronicle as a readable text saga.

    Returns the number of rows written. The whole record goes out
    (min_salience 1) - the book keeps what the screen elides.
    """
    from sandkings import SEASONS, SEASON_LENGTH, YEAR_LENGTH
    rows = getattr(sim, 'chronicle', None) or []
    epithets = getattr(sim, 'house_epithets', None) or {}
    lines = ["THE SAGA OF THE TERRARIUM", "=" * 40, ""]
    if epithets:
        lines.append("The houses, as history judged them:")
        for house, epithet in sorted(epithets.items()):
            lines.append(f"  House {house}, {epithet}")
        lines.append("")
    last_year = -1
    for step, text, _salience in rows:
        year = step // YEAR_LENGTH
        if year != last_year:
            last_year = year
            lines += ["", f"-- In the year {year + 1} --"]
        season = SEASONS[(step // SEASON_LENGTH) % 4]
        lines.append(f"  {season:>6}: {text}")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return len(rows)
