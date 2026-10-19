"""Enum dei flag di razze e mob (ROM): copia di `pachimud.character.race.enums`, verificata da `tests/test_game_compat.py`.

Servono a `apps/content` (opzioni dei form e controllo dei nomi nei YAML delle razze); l'editor non importa `pachimud`.
"""

from enum import IntEnum, IntFlag, auto

"""
ACT bits for mobs.
Used in #MOBILES.
"""


class MobileFlags(IntFlag):
    IS_NPC = auto()
    SCAVENGER = auto()  # Picks up objects
    UNUSED_FLAG_1 = auto()  # old: isnpc
    UNUSED_FLAG_2 = auto()  # old: nice_thief
    AGGRESSIVE = auto()  # Attacks PC's
    STAY_AREA = auto()  # Won't leave area
    WIMPY = auto()
    PET = auto()  # Auto set for pets
    TRAIN = auto()  # Can train PC's
    PRACTICE = auto()  # Can practice PC's
    UNUSED_FLAG_3 = auto()
    UNUSED_FLAG_4 = auto()
    UNUSED_FLAG_5 = auto()
    UNDEAD = auto()
    UNUSED_FLAG_6 = auto()
    CLERIC = auto()
    MAGE = auto()
    THIEF = auto()
    WARRIOR = auto()
    NOALIGN = auto()
    NOPURGE = auto()
    OUTDOORS = auto()
    UNUSED_FLAG_7 = auto()
    INDOORS = auto()
    UNUSED_FLAG_8 = auto()
    IS_HEALER = auto()
    GAIN = auto()
    UPDATE_ALWAYS = auto()
    IS_CHANGER = auto()
    MOB_FRIENDLY = TRAIN | PRACTICE | IS_HEALER | IS_CHANGER


# /* OFF bits for mobiles */
class OffensiveFlags(IntFlag):
    AREA_ATTACK = auto()
    BACKSTAB = auto()
    BASH = auto()
    BERSERK = auto()
    DISARM = auto()
    DODGE = auto()
    FADE = auto()
    FAST = auto()
    KICK = auto()
    KICK_DIRT = auto()
    PARRY = auto()
    RESCUE = auto()
    TAIL = auto()
    TRIP = auto()
    CRUSH = auto()
    ASSIST_ALL = auto()
    ASSIST_ALIGN = auto()
    ASSIST_RACE = auto()
    ASSIST_PLAYERS = auto()
    ASSIST_GUARD = auto()
    ASSIST_VNUM = auto()


# /* IMM/RES/VULN bits for mobs */
class ResistanceFlags(IntFlag):
    SUMMON = auto()
    CHARM = auto()
    MAGIC = auto()
    WEAPON = auto()
    BASH = auto()
    PIERCE = auto()
    SLASH = auto()
    FIRE = auto()
    COLD = auto()
    LIGHTNING = auto()
    ACID = auto()
    POISON = auto()
    NEGATIVE = auto()
    HOLY = auto()
    ENERGY = auto()
    MENTAL = auto()
    DISEASE = auto()
    DROWNING = auto()
    LIGHT = auto()
    SOUND = auto()
    UNUSED_FLAG_1 = auto()
    UNUSED_FLAG_2 = auto()
    UNUSED_FLAG_3 = auto()
    WOOD = auto()
    SILVER = auto()
    IRON = auto()


class FormFlags(IntFlag):
    # /* body form */
    EDIBLE = auto()
    POISON = auto()
    MAGICAL = auto()
    INSTANT_DECAY = auto()
    OTHER = auto()  # defined by material bit
    UNUSED_FLAG_1 = auto()

    # /* actual form */
    ANIMAL = auto()
    SENTIENT = auto()
    UNDEAD = auto()
    CONSTRUCT = auto()
    MIST = auto()
    INTANGIBLE = auto()
    BIPED = auto()
    CENTAUR = auto()
    INSECT = auto()
    SPIDER = auto()
    CRUSTACEAN = auto()
    WORM = auto()
    BLOB = auto()
    UNUSED_FLAG_2 = auto()
    UNUSED_FLAG_3 = auto()
    BASE_MAMMAL = auto()
    BASE_BIRD = auto()
    REPTILE = auto()
    SNAKE = auto()
    DRAGON = auto()
    AMPHIBIAN = auto()
    FISH = auto()
    COLD_BLOOD = auto()

    HUMANOID = EDIBLE | SENTIENT | BIPED | BASE_MAMMAL
    MAMMAL = EDIBLE | BASE_MAMMAL | ANIMAL
    BIRD = EDIBLE | BASE_BIRD | ANIMAL
    BUG = EDIBLE | ANIMAL | INSECT


# /* body parts */
class PartFlags(IntFlag):
    HEAD = auto()
    ARMS = auto()
    LEGS = auto()
    HEART = auto()
    BRAINS = auto()
    GUTS = auto()
    HANDS = auto()
    FEET = auto()
    FINGERS = auto()
    EAR = auto()
    EYE = auto()
    LONG_TONGUE = auto()
    EYESTALKS = auto()
    TENTACLES = auto()
    FINS = auto()
    WINGS = auto()
    TAIL = auto()
    UNUSED_FLAG_1 = auto()
    UNUSED_FLAG_2 = auto()
    UNUSED_FLAG_3 = auto()
    CLAWS = auto()  # for combat
    FANGS = auto()
    HORNS = auto()
    SCALES = auto()
    TUSKS = auto()

    ALIVE = HEART | BRAINS | GUTS
    QUADRUPED = HEAD | LEGS | ALIVE | FEET | EAR | EYE
    BIPED = HEAD | ARMS | LEGS | ALIVE | FEET | EAR | EYE
    HUMANOID = BIPED | HANDS | FINGERS

    FELINE = QUADRUPED | FANGS | TAIL | CLAWS
    CANINE = QUADRUPED | FANGS
    REPTILE = ALIVE | HEAD | EYE | LONG_TONGUE | TAIL | SCALES
    LIZARD = QUADRUPED | REPTILE
    BIRD = ALIVE | HEAD | LEGS | FEET | EYE | WINGS


# /* Bits for 'affected_by'.
#  * Used in #MOBILES.  */
class AffectedByFlags(IntFlag):
    BLIND = auto()
    INVISIBLE = auto()
    DETECT_EVIL = auto()
    DETECT_INVIS = auto()
    DETECT_MAGIC = auto()
    DETECT_HIDDEN = auto()
    DETECT_GOOD = auto()
    SANCTUARY = auto()
    FAERIE_FIRE = auto()
    INFRARED = auto()
    CURSE = auto()
    UNUSED_FLAG_1 = auto()  # old: flaming
    POISON = auto()
    PROTECT_EVIL = auto()
    PROTECT_GOOD = auto()
    SNEAK = auto()
    HIDE = auto()
    SLEEP = auto()
    CHARM = auto()
    FLYING = auto()
    PASS_DOOR = auto()
    HASTE = auto()
    CALM = auto()
    PLAGUE = auto()
    WEAKEN = auto()
    DARK_VISION = auto()
    BERSERK = auto()
    SWIM = auto()
    REGENERATION = auto()
    SLOW = auto()


# const SIZE_TYPE size_table[SIZE_MAX_R + 1] = {
class SizeType(IntEnum):
    TINY = auto()
    SMALL = auto()
    MEDIUM = auto()
    LARGE = auto()
    HUGE = auto()
    GIANT = auto()
