"""Tabelle di corrispondenza BasedMud/ROM <-> pivot (slot di vestizione dei reset `E`)."""

SLOT_ROM_TO_PIVOT: dict[str, str] = {
    "light": "light", "lfinger": "finger", "rfinger": "finger", "neck1": "neck", "neck2": "neck", "body": "body",
    "head": "head", "legs": "legs", "feet": "feet", "hands": "hands", "arms": "arms", "shield": "shield",
    "about": "about", "waist": "waist", "lwrist": "wrist", "rwrist": "wrist", "wielded": "wield", "hold": "hold",
    "floating": "floating",
}  # fmt: skip
SLOT_PIVOT_TO_ROM: dict[str, str] = {
    "light": "light", "finger": "lfinger", "neck": "neck1", "body": "body", "head": "head", "legs": "legs",
    "feet": "feet", "hands": "hands", "arms": "arms", "shield": "shield", "about": "about", "waist": "waist",
    "wrist": "lwrist", "wield": "wielded", "hold": "hold", "floating": "floating",
}  # fmt: skip
