"""Tabelle di corrispondenza condivise dei convertitori (vocabolario "pivot").

Il vocabolario "pivot" e' quello di pachimud, che segue ROM: nomi di flag ROM in minuscolo, tipi di danno `Direction`/`SectorType`
di pachimud, AC in scala piccola (`-10..10`, come Diku Modificato e i dati importati di pachimud; ROM la tiene x10), slot di
vestizione col nome del flag di vestibilita' (`wield`, `body`, ...). Ogni tabella e' `nome sorgente -> nome pivot`;
quelle inverse si ricavano con `invert`. Cio' che non e' in tabella viene scartato con una perdita. Le tabelle specifiche
di un mondo stanno nel pacchetto del suo adapter.
"""


def invert(table: dict[str, str]) -> dict[str, str]:
    """La tabella inversa (a parita' di valore vince la prima voce)."""
    out: dict[str, str] = {}
    for key, value in table.items():
        out.setdefault(value, key)
    return out


ACT_ROM_SILENT = frozenset({"npc"})
"""Il flag `npc` dei mob ROM e' implicito e non si riporta."""

# --------------------------------------------------------------------------- tipo di colpo delle armi

ATTACK_ROM_TO_OFFSET: dict[str, int] = {
    "none": 0, "slap": 0, "sting": 1, "whip": 2, "slash": 3, "slice": 3, "cleave": 3, "chop": 3, "bite": 4,
    "chomp": 4, "shbite": 4, "flbite": 4, "frbite": 4, "acbite": 4, "beating": 5, "crush": 6, "pound": 7,
    "smash": 7, "thwack": 7, "claw": 8, "scratch": 8, "pierce": 11, "stab": 11, "thrust": 11, "peck": 11,
    "peckb": 11, "blast": 12, "punch": 13,
}  # fmt: skip
"""Nome del colpo ROM -> scostamento da `TYPE_HIT` usato da pachimud (11 = perforante). Altri nomi -> 0 (colpo generico)."""
ATTACK_OFFSET_TO_ROM: dict[int, str] = {
    0: "punch", 1: "sting", 2: "whip", 3: "slash", 4: "bite", 5: "beating", 6: "crush", 7: "pound", 8: "claw",
    9: "crush", 10: "beating", 11: "pierce", 12: "blast", 13: "punch", 14: "stab",
}  # fmt: skip
