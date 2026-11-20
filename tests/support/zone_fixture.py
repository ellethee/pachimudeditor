"""Una cartella di zona "ricca" nel formato YAML del gioco, per i test di round-trip editor <-> file.

Copre ogni campo: uscite in tutte le direzioni con porte/chiavi/blocchi, extra description, rate/clan/owner, area su file
(`rooms_cantine.yaml`) e su voce, dadi con bonus negativo, razza/classe/insegnamenti e statistiche dei mob, oggetti di piu'
tipi (con i loro campi), `affects`, e reset con contenuti annidati, inventario con slot e porte. Contiene un commento YAML
per verificare che le scritture lo conservino.
"""

from pathlib import Path

ZONE = """\
---
zone_id: terra_di_prova
vnum: 88
name: Terra di Prova
builder: Tester
description: Una zona di prova.
bottom_vnum: 8800
top_vnum: 8899
min_level: 3
max_level: 12
lifespan_minutes: 20
reset_mode: EMPTY
enabled: false
"""

ROOMS = """\
---
rooms:
  # l'atrio: il cuore della zona
  - vnum: 8800
    name: Atrio
    description: |
      Un atrio con piu' righe.
      Seconda riga con accento: perche'.
    sector_type: CITY
    flags: [DARK, INDOORS]
    heal_rate: 150
    mana_rate: 80
    clan_id: lupi
    owner: Mario
    exits:
      north:
        target_vnum: 8801
        description: Una porta robusta.
        keywords: porta robusta
        door_flag: PICKPROOF
        is_open: false
        is_locked: true
        key_vnum: 8800
      east:
        target_vnum: 8802
      up:
        target_vnum: 99999
    extra_descriptions:
      - keywords: statua
        text: Una statua muta.
      - keywords: arazzo
        text: |
          Un arazzo
          molto antico.
  - vnum: 8801
    name: Sala
    description: Una sala.
    sector_type: INSIDE
    exits:
      south:
        target_vnum: 8800
        door_flag: CLOSABLE
        keywords: porta
  - vnum: 8802
    name: Giardino
    description: Un giardino.
    sector_type: FOREST
    flags: []
    exits:
      west:
        target_vnum: 8800
      down:
        description: Un buco nel nulla.
"""

ROOMS_CANTINE = """\
rooms:
  - vnum: 8803
    name: Cantina
    description: Una cantina umida.
    sector_type: UNDERWATER
    enabled: false
    exits:
      up:
        target_vnum: 8800
"""

MOBS = """\
---
mobs:
  - vnum: 8800
    keywords: guardia
    short_description: una guardia
    long_description: Una guardia sorveglia qui.
    detailed_description: |
      Una guardia severa.
    level: 7
    thac0: 15
    armor_class: -20
    hp_dice: 3d8+10
    damage_dice: 2d6+-1
    strength: 16
    dexterity: 12
    gold: 120
    experience: 450
    sex: MALE
    flags: [SENTINEL, AGGRESSIVE]
    alignment: -350
    race_id: human
    class_id: warrior
    debuff_skill_id: curse
    shop_id: armeria
    quest_ids: [q1, q2]
    is_banker: true
    teaches_class_ids: [warrior]
    teaches_skill_ids: [bash, kick]
  - vnum: 8801
    keywords: topo
    short_description: un topo
    long_description: Un topo corre.
    detailed_description: Un topo.
    level: 1
    thac0: 20
    armor_class: 0
    hp_dice: 1d4+0
    damage_dice: 1d2+0
"""

OBJECTS = """\
---
objects:
  - vnum: 8800
    keywords: chiave ottone
    short_description: una chiave d'ottone
    long_description: Una chiave d'ottone giace qui.
    action_description: Clic!
    object_type: KEY
    weight: 1
    cost: 5
    rent: 1
    key_type: 3
  - vnum: 8801
    keywords: spada lunga
    short_description: una spada lunga
    long_description: Una spada lunga.
    object_type: WEAPON
    weight: 12
    cost: 300
    rent: 10
    dice_count: 2
    die_size: 6
    weapon_type: 11
    extra_flags: [MAGIC, GLOW]
    wear_flags: [TAKE, WIELD]
    affects:
      STRENGTH: 2
      ARMOR_CLASS: -5
  - vnum: 8802
    keywords: sacca
    short_description: una sacca
    long_description: Una sacca.
    object_type: CONTAINER
    weight: 2
    cost: 10
    rent: 1
    max_weight: 50
    container_flags: [CLOSEABLE, LOCKED]
    key_vnum: 8800
  - vnum: 8803
    keywords: fiasca
    short_description: una fiasca
    long_description: Una fiasca.
    object_type: DRINKCON
    capacity: 10
    units: 4
    liquid: wine
    poisoned: true
  - vnum: 8804
    keywords: pozione
    short_description: una pozione
    long_description: Una pozione.
    object_type: POTION
    level: 5
    spells: [armor, bless]
"""

RESETS = """\
---
resets:
  objects:
    - obj_vnum: 8802
      max_existing: 1
      room_vnum: 8802
      room_limit: 1
      contains:
        - obj_vnum: 8800
          max_existing: 1
  mobs:
    - mob_vnum: 8800
      max_existing: 2
      room_vnum: 8800
      room_limit: 1
      inventory:
        - obj_vnum: 8800
          max_existing: 1
        - obj_vnum: 8801
          max_existing: 1
          wear_slot: WIELD
  doors:
    - room_vnum: 8800
      direction: NORTH
      state: LOCKED
"""

FILES = {
    "zone.yaml": ZONE,
    "rooms.yaml": ROOMS,
    "rooms_cantine.yaml": ROOMS_CANTINE,
    "mobs.yaml": MOBS,
    "objects.yaml": OBJECTS,
    "resets.yaml": RESETS,
}


def write_zone(directory: Path) -> Path:
    """Scrive i file in `directory` (creata) e la restituisce."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in FILES.items():
        (directory / name).write_text(text, encoding="utf-8")
    return directory
