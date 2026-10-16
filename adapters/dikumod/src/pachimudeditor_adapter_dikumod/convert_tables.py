"""Tabelle di corrispondenza Diku Modificato <-> pivot (vocabolario ROM/pachimud, vedi `pachimudeditor.sdk.convert_tables`)."""

# --------------------------------------------------------------------------- flag (Diku Modificato -> pivot/ROM)

ACT_DIKUMOD_TO_ROM: dict[str, str] = {
    "sentinel": "sentinel", "scavenger": "scavenger", "aggressive": "aggressive", "stay_zone": "stay_area",
    "wimpy": "wimpy", "magic_user": "mage", "warrior": "warrior", "cleric": "cleric", "thief": "thief",
}  # fmt: skip
"""Flag `act` dei mob: Diku Modificato -> ROM. `isnpc` (Diku Modificato) e `npc` (ROM) sono impliciti e non si riportano."""
ACT_DIKUMOD_SILENT = frozenset({"isnpc"})

ROOM_DIKUMOD_TO_ROM: dict[str, str] = {
    "dark": "dark", "no_mob": "no_mob", "indoors": "indoors", "private": "private", "peaceful": "safe",
}  # fmt: skip

EXTRA_DIKUMOD_TO_ROM: dict[str, str] = {
    "glow": "glow", "hum": "hum", "magic": "magic", "nodrop": "nodrop", "bless": "bless", "invisible": "invis",
    "anti_good": "antigood", "anti_evil": "antievil", "anti_neutral": "antineutral",
}  # fmt: skip
"""Flag extra degli oggetti: Diku Modificato -> ROM."""

WEAR_DIKUMOD_TO_ROM: dict[str, str] = {
    "take": "take", "finger": "finger", "neck": "neck", "body": "body", "head": "head", "legs": "legs", "feet": "feet",
    "hands": "hands", "arms": "arms", "shield": "shield", "about": "about", "waiste": "waist", "wrist": "wrist",
    "wield": "wield", "hold": "hold",
}  # fmt: skip
"""Flag di vestibilita': Diku Modificato -> ROM (`back`, `ear`, `eye`, `throw` non esistono in ROM)."""

# --------------------------------------------------------------------------- apply degli oggetti

APPLY_DIKUMOD_TO_ROM: dict[str, str] = {
    "str": "strength", "dex": "dexterity", "int": "intelligence", "wis": "wisdom", "con": "constitution",
    "sex": "sex", "level": "level", "age": "age", "char_weight": "weight", "char_height": "height", "mana": "mana",
    "hit": "hp", "move": "moves", "gold": "gold", "exp": "experience", "ac": "armor class", "hitroll": "hit roll",
    "damroll": "damage roll", "saving_para": "saves", "saving_rod": "save vs rod",
    "saving_petri": "save vs petrification", "saving_breath": "save vs breath", "saving_spell": "save vs spell",
}  # fmt: skip
"""Nomi di `apply`: Diku Modificato -> ROM (gli altri, es. `chr`, `backstab`, non esistono in ROM)."""

# --------------------------------------------------------------------------- slot di vestizione dei reset `E`

SLOT_DIKUMOD_TO_PIVOT: dict[str, str] = {
    "light": "light", "finger_r": "finger", "finger_l": "finger", "neck_1": "neck", "neck_2": "neck", "body": "body",
    "head": "head", "legs": "legs", "feet": "feet", "hands": "hands", "arms": "arms", "shield": "shield",
    "about": "about", "waiste": "waist", "wrist_r": "wrist", "wrist_l": "wrist", "wield": "wield", "hold": "hold",
    "back": "back", "ear_r": "ear", "ear_l": "ear", "eyes": "eye",
}  # fmt: skip
SLOT_PIVOT_TO_DIKUMOD: dict[str, str] = {
    "light": "light", "finger": "finger_r", "neck": "neck_1", "body": "body", "head": "head", "legs": "legs",
    "feet": "feet", "hands": "hands", "arms": "arms", "shield": "shield", "about": "about", "waist": "waiste",
    "wrist": "wrist_r", "wield": "wield", "hold": "hold", "back": "back", "ear": "ear_r", "eye": "eyes",
}  # fmt: skip

# --------------------------------------------------------------------------- razze

RACE_DIKUMOD_TO_PIVOT: dict[str, str] = {
    "elven": "elf", "gold_elf": "elf", "wild_elf": "elf", "sea_elf": "elf", "half_elven": "elf", "dark_dwarf": "dwarf",
    "lizardman": "lizard", "reptile": "lizard", "half_orc": "orc", "bird": "song_bird", "predator": "wolf",
    "giant_hill": "giant", "giant_frost": "giant", "giant_fire": "giant", "giant_cloud": "giant",
    "giant_storm": "giant", "giant_stone": "giant", "half_giant": "giant",
}  # fmt: skip
"""Razze Diku Modificato senza lo stesso nome tra quelle di pachimud -> razza vicina (le `dragon_*` sono gestite a parte)."""
RACE_PIVOT_TO_DIKUMOD: dict[str, str] = {
    "elf": "elven", "lizard": "lizardman", "song_bird": "bird", "water_fowl": "bird", "wolf": "predator",
    "dog": "predator", "fido": "predator", "cat": "predator", "bear": "predator", "fox": "predator",
    "wyvern": "dragon", "hobgoblin": "goblin", "kobold": "goblin",
}  # fmt: skip
