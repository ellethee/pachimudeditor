"""Tabelle di Diku Modificato (da `structs.h`/`race.h`): bit -> nome per i flag, indice -> nome per i tipi.

I nomi sono minuscoli (`dark`, `no_mob`, ...). I bit non noti si chiamano `bitN` (N = esponente): `names_to_flags` li
riaccetta, cosi' il round-trip non perde nulla.
"""

from __future__ import annotations

from collections.abc import Iterable


def _bits(names: str) -> dict[str, int]:
    """`{nome: 1 << posizione}` da una lista separata da virgole (posizioni consecutive dal bit 0)."""
    return {n.strip(): 1 << i for i, n in enumerate(names.split(","))}


def _list(names: str) -> list[str]:
    """Lista di nomi separati da virgole."""
    return [n.strip() for n in names.split(",")]


ROOM_FLAGS = _bits(
    "dark,death,no_mob,indoors,peaceful,no_steal,no_summon,no_magic,tunnel,private,silence,large,no_death,save_room,"
    "no_track,no_mind,desertic,artic,underground,hot,wet,cold,dry,bright,no_astral,no_regain"
)
EXIT_FLAGS = _bits("isdoor,closed,locked,secret,notbash,pickproof,climb,male,nolookt,noknock,invis")
ACT_FLAGS = _bits(
    "nochase,sentinel,scavenger,isnpc,nice_thief,aggressive,stay_zone,wimpy,annoying,hateful,afraid,immortal,hunting,"
    "deadly,polyself,meta_agg,guardian,illusion,huge,script,greet,magic_user,warrior,cleric,thief,druid,monk,barbarian,"
    "paladin,ranger,psi,archer"
)
AFFECT_FLAGS = _bits(
    "blind,invisible,detect_evil,detect_invisible,detect_magic,sense_life,life_prot,sanctuary,dragon_ride,growth,curse,"
    "flying,poison,tree_travel,paralysis,infravision,waterbreath,sleep,travelling,sneak,hide,silence,charm,follow,"
    "protect_from_evil,true_sight,scrying,fireshield,group,telepathy"
)
IMMUNE_FLAGS = _bits(
    "fire,cold,elec,energy,blunt,pierce,slash,acid,poison,drain,sleep,charm,hold,nonmag,plus1,plus2,plus3,plus4"
)
EXTRA_FLAGS = _bits(
    "glow,hum,metal,mineral,organic,invisible,magic,nodrop,bless,anti_good,anti_evil,anti_neutral,anti_cleric,anti_mage,"
    "anti_thief,anti_fighter,brittle,resistant,immune,anti_men,anti_women,anti_sun,anti_barbarian,anti_ranger,"
    "anti_paladin,anti_psi,anti_monk,anti_druid,only_class,dig,scythe"
)
WEAR_FLAGS = {
    "take": 1, "finger": 2, "neck": 4, "body": 8, "head": 16, "legs": 32, "feet": 64, "hands": 128, "arms": 256,
    "shield": 512, "about": 1024, "waiste": 2048, "wrist": 4096, "wield": 8192, "hold": 16384, "throw": 32768,
    "back": 131072, "ear": 262144, "eye": 524288,
}  # fmt: skip
TELE_FLAGS = {"look": 1, "count": 2, "random": 4, "spin": 8, "no_mob": 16}
ZONE_RESET_BITS = {"empty": 1, "always": 2, "astral": 4, "desert": 8, "arctic": 16, "underground": 32}

FLAG_TABLES: dict[str, dict[str, int]] = {
    "room_flags": ROOM_FLAGS,
    "exit_flags": EXIT_FLAGS,
    "act_flags": ACT_FLAGS,
    "affect_flags": AFFECT_FLAGS,
    "immune_flags": IMMUNE_FLAGS,
    "extra_flags": EXTRA_FLAGS,
    "wear_flags": WEAR_FLAGS,
    "tele_flags": TELE_FLAGS,
}

SECTORS = _list(
    "inside,city,field,forest,hills,mountain,water_swim,water_noswim,air,underwater,desert,tree,darkcity"
)
ITEM_TYPES = _list(
    "none,light,scroll,wand,staff,weapon,fireweapon,missile,treasure,armor,potion,worn,other,trash,trap,container,"
    "note,drinkcon,key,food,money,pen,boat,audio,board,tree,rock"
)
POSITIONS = _list("dead,mortallyw,incap,stunned,sleeping,resting,sitting,fighting,standing,mounted")
SEXES = _list("neutral,male,female")
APPLY_TYPES = _list(
    "none,str,dex,int,wis,con,chr,sex,level,age,char_weight,char_height,mana,hit,move,gold,exp,ac,hitroll,damroll,"
    "saving_para,saving_rod,saving_petri,saving_breath,saving_spell,save_all,immune,susc,m_immune,spell,weapon_spell,"
    "eat_spell,backstab,kick,sneak,hide,bash,pick,steal,track,hitndam,spellfail,attacks,haste,slow,bv2,find_traps,ride,"
    "race_slayer,align_slayer,mana_regen,hit_regen,move_regen,mod_thirst,mod_hunger,mod_drunk,t_str,t_int,t_dex,t_wis,"
    "t_con,t_chr,t_hps,t_move,t_mana"
)
WEAR_POSITIONS = _list(
    "light,finger_r,finger_l,neck_1,neck_2,body,head,legs,feet,hands,arms,shield,about,waiste,wrist_r,wrist_l,wield,"
    "hold,back,ear_r,ear_l,eyes,loaded_weapon"
)
RACES = _list(
    "halfbreed,human,elven,dwarf,halfling,gnome,reptile,special,lycanth,dragon,undead,orc,insect,arachnid,dinosaur,fish,"
    "bird,giant,predator,parasite,slime,demon,snake,herbiv,tree,veggie,element,planar,devil,ghost,goblin,troll,vegman,"
    "mflayer,primate,enfan,drow,golem,skexie,trogman,patryn,labrat,sartan,tytan,smurf,roo,horse,draagdim,astral,god,"
    "giant_hill,giant_frost,giant_fire,giant_cloud,giant_storm,giant_stone,dragon_red,dragon_black,dragon_green,"
    "dragon_white,dragon_blue,dragon_silver,dragon_gold,dragon_bronze,dragon_copper,dragon_brass,undead_vampire,"
    "undead_lich,undead_wight,undead_ghast,undead_spectre,undead_zombie,undead_skeleton,undead_ghoul,half_elven,"
    "half_ogre,half_orc,half_giant,lizardman,dark_dwarf,deep_gnome,gnoll,gold_elf,wild_elf,sea_elf"
)
DOOR_STATES = ["OPEN", "CLOSED", "LOCKED"]
"""Stato iniziale della porta nei comandi `D`: 0 aperta, 1 chiusa, 2 chiusa e serrata."""
HATE_FEAR_TYPES = {1: "sex", 2: "race", 3: "forbidden", 4: "class", 5: "evil", 6: "good", 7: "mob_vnum"}
LIQUIDS = _list(
    "water,beer,wine,ale,darkale,whisky,lemonade,firebrt,localspc,slime,milk,tea,coffe,blood,saltwater,coke"
)

TYPE_TABLES: dict[str, list[str]] = {
    "sectors": SECTORS,
    "item_types": ITEM_TYPES,
    "positions": POSITIONS,
    "sexes": SEXES,
    "apply_types": APPLY_TYPES,
    "wear_positions": WEAR_POSITIONS,
    "races": RACES,
    "liquids": LIQUIDS,
}

ZONE_COMMANDS = "MOGEPDCHFZ"
"""Lettere dei comandi di reset note al loader (`R` documentata ma non implementata)."""
ZONE_ARG_COUNT: dict[str, int] = {"M": 3, "O": 4, "G": 2, "E": 3, "P": 3, "D": 3, "C": 3, "H": 2, "F": 2, "Z": 2}
"""Numero di argomenti numerici dopo `if_flag`. `O` ne vuole 4 (obj max room max_in_room); il parser tollera 3."""
ZONE_ARG_NAMES: dict[str, tuple[str, ...]] = {
    "M": ("mob", "max", "room"),
    "O": ("obj", "max", "room", "max_in_room"),
    "G": ("obj", "max"),
    "E": ("obj", "max", "wear_pos"),
    "P": ("obj", "max", "container"),
    "D": ("room", "dir", "state"),
    "C": ("mob", "max", "act_bits"),
    "H": ("type", "value"),
    "F": ("type", "value"),
    "Z": ("zone", "flag"),
}


def flag_names(table: dict[str, int], value: int) -> list[str]:
    """Nomi dei bit accesi in `value`, in ordine di bit; i bit senza nome sono `bitN`."""
    out: list[str] = []
    known = {bit: name for name, bit in table.items()}
    v = value & 0xFFFFFFFF if value >= 0 else value & 0xFFFFFFFF
    for i in range(32):
        bit = 1 << i
        if v & bit:
            out.append(known.get(bit, f"bit{i}"))
    return out


def names_to_flags(table: dict[str, int], names: Iterable[str]) -> int:
    """Valore intero dei nomi (o `bitN`); `KeyError(nome)` se non esiste."""
    value = 0
    for name in names:
        key = name.strip().lower()
        if key in table:
            value |= table[key]
        elif key.startswith("bit") and key[3:].isdigit():
            value |= 1 << int(key[3:])
        else:
            raise KeyError(name)
    return value


def type_name(table: list[str], index: int) -> str:
    """Nome dell'indice (o il numero come testo se fuori tabella)."""
    return table[index] if 0 <= index < len(table) else str(index)
