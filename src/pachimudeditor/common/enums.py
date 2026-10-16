"""Enumerazioni neutre dell'editor: copie dei valori di `pachimud.*.enums` (IntEnum con gli stessi nomi e valori).

Servono ai DTO, alle regole e agli adapter su file (basedmud, dikumod, mapping) senza importare `pachimud`, che resta
opzionale. Essendo `IntEnum`, un membro di `pachimud` e uno di qui sono intercambiabili (uguaglianza, hash, JSON,
colonne intere). `tests/test_enums_sync.py` verifica l'allineamento con `pachimud` quando e' importabile.
"""

from enum import IntEnum


class Sex(IntEnum):
    """Grammatical/biological sex of a mob prototype."""

    NEUTRAL = 0
    MALE = 1
    FEMALE = 2
    BOTH = 3


class Position(IntEnum):
    """Position or posture of a mob."""

    DEAD = 0
    MORTAL = 1
    INCAP = 2
    STUNNED = 3
    SLEEPING = 4
    RESTING = 5
    SITTING = 6
    FIGHTING = 7
    STANDING = 8


class ObjectType(IntEnum):
    """What kind of object a prototype describes; governs value_0..value_3 meaning."""

    LIGHT = 0
    WEAPON = 1
    ARMOR = 2
    CONTAINER = 3
    LIQUID_CONTAINER = 4
    TREASURE = 5
    OTHER = 6
    TRASH = 7
    KEY = 8
    FOOD = 9
    MONEY = 10
    POTION = 11
    SCROLL = 12
    WAND = 13
    STAFF = 14
    FOUNTAIN = 15


class ZoneCommandType(IntEnum):
    """A zone reset command, named after ROM's M/O/G/E/P/D/R letters (`reset_data`,
    `db.c::load_resets`) - not tbaMUD's, which reuses the same letters with different meaning."""

    LOAD_MOB = 0
    LOAD_OBJECT = 1
    GIVE_OBJECT = 2
    EQUIP_OBJECT = 3
    PUT_OBJECT = 4
    SET_DOOR_STATE = 5
    RANDOMIZE_EXITS = 6
    """ROM's 'R': shuffles which exit leads where among the room's existing doors, for
    maze-like areas (`db.c` case 'R'). Distinct from tbaMUD's 'R', which removes an object
    from a room before other resets run - not ported here."""


class ZoneResetMode(IntEnum):
    """Controls whether/when a zone's reset commands re-run."""

    NEVER = 0
    EMPTY = 1
    ALWAYS = 2


class SectorType(IntEnum):
    """Terrain type of a room; affects movement cost and light rules."""

    INSIDE = 0
    CITY = 1
    FIELD = 2
    FOREST = 3
    HILLS = 4
    MOUNTAIN = 5
    WATER_SWIM = 6
    WATER_NOSWIM = 7
    FLYING = 8
    UNDERWATER = 9


class Direction(IntEnum):
    """One of a room's up-to-six exits."""

    NORTH = 0
    EAST = 1
    SOUTH = 2
    WEST = 3
    UP = 4
    DOWN = 5


class DoorFlag(IntEnum):
    """Whether an exit has a door and how it can be manipulated."""

    NONE = 0
    CLOSABLE = 1
    PICKPROOF = 2
