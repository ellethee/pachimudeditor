# Copia di pachimud/character/enums.py (MUD pachimud, ROM-like).
# COPIA: mantenere allineata con il MUD (vedi docs/contributing.md, sezione "Mantenere i modelli allineati col MUD").
# Le enum dei contenuti (oggetti, zone, stanze) sono in `pachimudeditor.common.enums`.

from enum import IntEnum


# --- pachimud/character/enums.py


class Sex(IntEnum):
    """Grammatical/biological sex of a mob prototype."""

    NEUTRAL = 0
    MALE = 1
    FEMALE = 2
    BOTH = 3


class Position(IntEnum):
    """Position or posture of a mob."""

    DEAD = 0
    MORTALLY_WOUNDED = 1
    INCAPACITATED = 2
    STUNNED = 3
    SLEEPING = 4
    RESTING = 5
    SITTING = 6
    FIGHTING = 7
    STANDING = 8
    MOUNTED = 9
