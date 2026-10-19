"""Una cartella di zona "ricca" nel formato YAML del gioco, per i test di round-trip editor <-> importer.

Copre ogni campo dei cinque file: uscite in tutte le direzioni con porte/chiavi/blocchi, extra description, rate/clan/
owner, dadi con bonus negativo, razza/classe/insegnamenti dei mob, valori e `affects` degli oggetti, i sette tipi di reset.
"""

from pathlib import Path

ZONE = """\
---
zone_id: terra_di_prova
vnum: 88
name: Terra di Prova
builder: Tester
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
  - vnum: 8800
    name: Atrio
    description: |
      Un atrio con piu' righe.
      Seconda riga con accento: perche'.
    sector_type: CITY
    flags: [dark, indoors]
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
    gold: 120
    experience: 450
    sex: MALE
    flags: [sentinel, aggressive]
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
  - vnum: 8801
    keywords: spada lunga
    short_description: una spada lunga
    long_description: Una spada lunga.
    object_type: WEAPON
    weight: 12
    cost: 300
    rent: 10
    value_0: 2
    value_1: 6
    value_2: 1
    value_3: 3
    extra_flags: [magic, glow]
    wear_flags: [take, wield]
    affects:
      strength: 2
      armor_class: -5
  - vnum: 8802
    keywords: sacca
    short_description: una sacca
    long_description: Una sacca.
    object_type: CONTAINER
    weight: 2
    cost: 10
    rent: 1
    value_0: 5
"""

RESETS = """\
---
resets:
  - type: LOAD_MOB
    mob_vnum: 8800
    max_existing: 2
    room_vnum: 8800
    room_limit: 1
  - type: GIVE_OBJECT
    if_flag: true
    obj_vnum: 8800
    max_existing: 1
  - type: EQUIP_OBJECT
    if_flag: true
    obj_vnum: 8801
    max_existing: 1
    wear_slot: wield
  - type: LOAD_OBJECT
    obj_vnum: 8802
    max_existing: 1
    room_vnum: 8802
  - type: PUT_OBJECT
    obj_vnum: 8800
    max_existing: 1
    container_vnum: 8802
  - type: SET_DOOR_STATE
    room_vnum: 8800
    direction: NORTH
    state: LOCKED
  - type: RANDOMIZE_EXITS
    room_vnum: 8802
"""

FILES = {"zone.yaml": ZONE, "rooms.yaml": ROOMS, "mobs.yaml": MOBS, "objects.yaml": OBJECTS, "resets.yaml": RESETS}


def write_zone(directory: Path) -> Path:
    """Scrive i cinque file in `directory` (creata) e la restituisce."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in FILES.items():
        (directory / name).write_text(text, encoding="utf-8")
    return directory
