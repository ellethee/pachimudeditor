# Formato dati del Diku Modificato

Un Diku molto modificato: il formato su disco e' quello del DikuMUD classico con estensioni (mob `A/B/L/N`, flag
sommati con `|`, stanze teleport/fiume, reset `C H F Z`, override per-vnum, script e gilde). Questo documento descrive
la grammatica come la legge il caricatore del gioco (`db.c`, `db.h`, `structs.h`, `race.h`, `shop.c`, `mobact.c`,
`utility.c`). Dove i documenti Diku originali e il codice divergono **vale il codice** (i vecchi documenti descrivono ad
esempio ancora i "door flag" 0-7).

I file dati stanno in `lib/` e hanno il prefisso `dikumoddata.` (`dikumoddata.wld`, `.mob`, `.obj`, `.zon`, `.shp`): e' il
nome che cerca l'adapter `dikumod`. Non confonderlo con l'esempio del mapping generico `diku_classic.yaml`, che descrive
in YAML il Diku classico "un file per tipo" senza override per-vnum, script, gilde ne' tolleranza ai record corrotti
(vedi [adapter dikumod](../adapters/dikumod.md)).

## 1. Varianti

Il formato e il loader sono gli stessi per le due varianti riconosciute dall'adapter (`params.variant`):

* **`dikumod`**: solo i file principali `dikumoddata.{wld,mob,obj,zon,shp}`, `scripts.dat` e le cartelle `scripts/`.
* **`dikumod2`**: stesso formato, con in piu' (a) gli override per-vnum `rooms/` e `objects/` popolati, (b) file prodotti
  da un editor esterno (elencati qui di seguito), (c) il file gilde `dikumoddata.gui` + `gilde/`.

Nei dati le descrizioni delle uscite possono terminare con `\n` prima della `~`, e i **flag porta** possono essere
normalizzati in modo da avere sempre `EX_ISDOOR` (1) dove c'e' una porta (il loader lo "ripara" a runtime con
"Door error ... (fixed)" nei comandi `D`).

File accessori che un editor esterno puo' produrre (non letti dal MUD, non letti dall'adapter):

* `dikumoddata2.mob` / `dikumoddata2.obj`: esportazione parziale. Stessa grammatica, ma i flag sono scritti come `a|b|c`
  e l'ultimo record puo' mancare del terminatore `%%`.
* `dikumoddata3.mob` / `dikumoddata3.obj`: esportazione "canonica" dell'intero mondo (flag sempre `a|b|c`). **Lossy**
  (la riga `-1 <gold> <exp> <race>` puo' perdere exp/race): non e' una fonte affidabile.
* `dikumoddata4.zon`: puo' contenere zone *initlist* generate (riga nome `~` mancante, commenti `*! ...`): malformate per il loader.
* `dikumoddata.err`: log di validazione, **CP1252** (unico file con byte alti).
* `*~`, `*.new`, `gmon*.out`, `DEADJOE`: backup/rumore, da ignorare.

## 2. Codifica, fine riga, terminatori

* **Tutti** i file dati (`.wld .mob .obj .zon .shp .act .dam .pos`, `scripts/*`, help, `rooms/*`, `objects/*`) sono ASCII puro: 0 byte
  >= 0x80, 0 caratteri di controllo (verificato con `grep -P`). Gli accenti sono scritti con l'apice (`e'`, `citta'`, `perche'`). Unica eccezione
  `dikumoddata.err` (CP1252). Per sicurezza leggere come `latin-1` (round-trip byte-esatto) e scrivere uguale.
* Fine riga `\n` (0 `\r` nei file principali). Nei **file per-vnum scritti dal gioco** (`objects/*`) compaiono `\r\n` *dentro* i testi
  (`^M` nelle extra description), perche' `write_obj_to_file` non toglie i `\r` che `fread_string` aveva inserito. Il loader
  accetta (`\r` e' spazio). `RoomSave` (rsave) invece toglie i `\r`.
* Stringhe: testo libero (anche multi-riga) **terminato da `~`**. `fread_string` legge fino alla `~` e **scarta anche il
  carattere successivo** (di norma `\n`). Una `~` dentro il testo e' impossibile (non esiste escape); stringa vuota = `~`.
  Il C inserisce un `\r` dopo ogni `\n` in memoria (non e' nel file).
* Numeri: `fread_number`: spazi, segno `+/-`, cifre; se subito dopo c'e' `|` il valore e' la **somma** dei termini
  (`1|4|256` = 261). Il separatore e' uno spazio/newline; i flag sono scritti a *bit* (in somma, non OR: un bit ripetuto rompe il valore).
* Codici colore nel testo: `$c0007`, `$c1001`..., `$$c` (escape dentro `act()`), `$n $N $s` ecc. Non vanno toccati.
* Terminatori di file: `.wld` nessuno (EOF; `boot_world` si ferma quando `#%ld` non e' piu' leggibile); `.mob/.obj`
  riga che inizia per `%%` (`%%~` o `%%`), `.zon` e `.shp` record `$~` (`#9999999\n$~`; il `.shp` principale termina con `$~`).
  Il `#` di un nuovo record **deve essere al primo carattere della riga** per mob/oggetti (indicizzazione per righe).
* Dimensione massima di una stringa: `MAX_STRING_LENGTH` 20480 (oltre: errore e resync).

## 3. Layout dei file e caricamento (`boot_db`, `db.c`)

Cartella di lavoro = `lib/` (`DFLT_DIR "lib"`). Ordine di `boot_db`: `boot_zones` (`dikumoddata.zon`) -> `boot_saved_zones`
(`zones/<n>.zon`) -> `boot_world` (`dikumoddata.wld`) -> `boot_saved_rooms` (`rooms/<vnum>`) -> `generate_indices` mob (`dikumoddata.mob`,
`mobiles/`) e oggetti (`dikumoddata.obj`, `objects/`) -> `renum_zone_table` -> shop (`dikumoddata.shp`, in `spec_assign`) ->
script (`scripts.dat`) -> gilde (`dikumoddata.gui`) -> `ReloadRooms` (`world/<vnum>`).

| File/dir | Ruolo | Loader |
|---|---|---|
| `dikumoddata.zon` | **indice delle zone** + tabella comandi di reset di ciascuna | `boot_zones` |
| `dikumoddata.wld` | tutte le stanze, ordinate per vnum crescente | `boot_world` + `load_one_room` |
| `dikumoddata.mob` / `dikumoddata.obj` | prototipi, **accesso per offset** (`ftell` raccolto da `generate_indices`; lettura lazy con `fseek`) | `read_mobile`, `read_object` |
| `dikumoddata.shp` | negozi | `boot_the_shops` (shop.c) |
| `rooms/<vnum>` | override di **una** stanza (stesso grammar del `.wld`, header `#vnum` ignorato: conta `atoi(nome file)`) | `boot_saved_rooms`, `RoomLoad`; scritto da `RoomSave` (rsave) |
| `objects/<vnum>` | override/aggiunta di **un** oggetto (grammar `.obj`); se il vnum esiste anche nel `.obj` **vince il file** (`pos = -1`) | `generate_indices`, `read_object`; scritto da `osave` (`write_obj_to_file`) |
| `mobiles/<vnum>` | indicizzato ma **non caricabile** (`read_mobile` fa `fseek(pos=-1)`): vestigiale, vuoto in entrambi gli alberi | - |
| `zones/<n>.zon` | sostituisce la sola tabella comandi della zona di indice n (senza header; vedi 4.5) | `boot_saved_zones` -> `LoadZoneFile` |
| `world/<vnum>` | **binario** (struct `obj_file_u`) con gli oggetti salvati in una stanza `SAVE_ROOM`; non e' formato mondo | `load_room_objs` |
| `world/mobs.<0,1000,...>` | dump testuale di reset (`M ... Z H F E G`) del "static game" per la zona 0 (`SaveTheWorld`, `ReadTextZone`) | `reset_zone(0)` |
| `scripts.dat` + `scripts/<Nome>` | script dei mob (sez. 8) | `InitScripts` |
| `dikumoddata.gui` + `gilde/` | gilde (sez. 9) | `BootGuilds` |
| `killfile` | elenco vnum di mob da non caricare (uno per riga) | `CheckKillFile` |
| `dikumoddata.act/.pos/.dam` | social, pose, messaggi di combattimento: **non** parte del mondo | altri |

**Non esiste un `area.lst`**: ogni file contiene tutto il mondo; la mappa zona -> vnum e' dentro `dikumoddata.zon`.

### Come una zona delimita i vnum
Una zona ha solo un campo `top`. Una stanza appartiene alla **prima zona (per posizione nel file) con `top >= vnum`**
(`load_one_room`: `for(zone=0; vnum > zone_table[zone].top ...; zone++)`); bottom = `top` della zona precedente + 1 (zona 0 parte da 0).
Quindi: le zone devono comparire in ordine di `top` crescente (verificato: 0 violazioni), una stanza fuori da tutte le zone fa
`exit(1)` (0 casi). Mob e oggetti **non hanno una zona propria**: l'`id`/`zone_id` neutro si ricava dal vnum con lo stesso
intervallo (nessun vincolo del motore, solo convenzione e controlli dell'OLC `osave`).
Il numero `#N` della zona (`znumber`) **non e' un'identita'**: non e' univoco (`138`, `151` ripetuti in entrambi gli alberi,
`1400`, `24791` spurio) e il motore usa l'*indice* di posizione (`zone_table[i]`). Il comando reset `Z` e `specials.zone` usano
l'indice, non `#N`. Zona 0 = "Scratch Zone For Static Game" (`#1`, top 0, `0 0 0` senza comandi), zona di indice 1 = LIMBO.

Mob/oggetti: vnum **non devono essere ordinati** (ricerca nell'indice), ma i duplicati esistono: mob `3703 16053 19208 21356`,
oggetti `16056 16207 21361` compaiono due volte (in entrambi gli alberi); la `real_mobile/real_object` ne trova uno solo.

## 4. Grammatica dei record

Notazione: `<n>` intero, `<flags>` intero o somma `a|b|c`, `<s>~` stringa fino a `~`. Righe = convenzione; il C e' token-based.

### 4.1 Stanza (`.wld`, `rooms/<vnum>`)

```
#<vnum>
<name>~
<description>~
<zone_ignorata> <room_flags> <sector>
  se sector == -1:  <tele_time> <tele_target> <tele_mask> [<tele_count> se tele_mask & 2] <real_sector>
  se (real) sector in {7 WATER_NOSWIM, 9 UNDERWATER}:  <river_speed> <river_dir>
  se room_flags & 256 (TUNNEL):  <moblim>
{ D<0..5>
  <exit_description>~
  <keywords>~
  <exit_info> <key_vnum> <to_room> [<open_cmd>]
| E
  <keywords>~
  <description>~
| L
  <testo_notte>~
  <testo_giorno>~          (flag BRIGHT: lampioni)
| C <commento su una riga> }      (ignorato; in pratica mai usato)
S
```

* Il primo numero della riga numerica (`zone`) e' **letto e scartato** (`fscanf(" %*d ")`); la zona e' calcolata dal vnum. Nei dati e' spesso
  incoerente (`0`, `13`, `-1`). `RoomSave` scrive l'*indice* di zona.
* `exit_info`, `key`, `to_room`: `fread_number` (accettano `|`). `open_cmd` (comando che apre: `99 open`, `224 pull`, `371 twist`, `372 turn`,
  `373 lift`, `374 push`) e' letto con `fscanf(" %ld ")` e vale `-1` se assente.
  `key = -1` = nessuna chiave; `to_room = -1` = uscita senza destinazione. La descrizione dell'uscita inizia dopo `D<n>` e newline
  (il C salta **tutti** gli spazi dopo il token `D<n>`); termina con `\n~`.
* Dopo ogni token (`D2`, `E`, `S`) `fscanf(" %160s \n")` consuma gli spazi: righe vuote ripetute o rientri non cambiano nulla.
* Token ignoto -> `mudlog "unknown auxiliary code"` e **prosegue token per token**: un testo mal terminato fa derivare il parser.
* Uscite: `D0` nord, `D1` est, `D2` sud, `D3` ovest, `D4` su, `D5` giu' (max una per direzione; l'ultima vince).
  Le extra description sono inserite in testa alla lista (l'ordine in memoria e' inverso al file).
* Se i dati sono stati generati da un editor esterno, le descrizioni di uscita possono essere segnaposto del tipo `[3167 (stanza sconosciuta)]` / `[40004 (Nome stanza)]`:
  sono metadati dell'editor, non testo per i giocatori.

**Tabelle** (`structs.h`):

`room_flags` (bit): 1 DARK, 2 DEATH, 4 NO_MOB, 8 INDOORS, 16 PEACEFUL, 32 NO_STEAL, 64 NO_SUMMON, 128 NO_MAGIC, 256 TUNNEL, 512 PRIVATE,
1024 SILENCE, 2048 LARGE, 4096 NO_DEATH, 8192 SAVE_ROOM, 16384 NO_TRACK, 32768 NO_MIND, 65536 DESERTIC, 131072 ARTIC, 262144 UNDERGROUND,
524288 HOT, 1048576 WET, 2097152 COLD, 4194304 DRY, 8388608 BRIGHT, 16777216 NO_ASTRAL, 33554432 NO_REGAIN.

`sector`: 0 INSIDE, 1 CITY, 2 FIELD, 3 FOREST, 4 HILLS, 5 MOUNTAIN, 6 WATER_SWIM, 7 WATER_NOSWIM, 8 AIR, 9 UNDERWATER, 10 DESERT, 11 TREE,
12 DARKCITY, **-1 teleport** (seguito dal blocco tele e dal vero settore). `tele_mask`: 1 TELE_LOOK, 2 TELE_COUNT, 4 TELE_RANDOM, 8 TELE_SPIN,
16 TELE_NO_MOB. Direzione fiume `river_dir` 0..5 come le uscite.

`exit_info` (bit): 1 ISDOOR, 2 CLOSED, 4 LOCKED, 8 SECRET, 16 NOTBASH, 32 PICKPROOF, 64 CLIMB, 128 MALE, 256 NOLOOKT, 512 NOKNOCK, 1024 INVIS.
Stato iniziale = quello dei bit CLOSED/LOCKED nel file, poi **sovrascritto** dai comandi `D` della zona (il reset forza
ISDOOR se manca). Si trovano anche valori senza `ISDOOR` (es. `2`: "porta senza bit ISDOOR").

Esempio (stanza con uscita ed extra description):

```
#3008
La reception~
   Sei alla reception.
Un piccolo cartello spicca sul banco.
~
13 92 0
D1
Un corridoio verso l'ufficio
~
~
0 -1 3065 -1
E
sign cartello~
Un testo di esempio.
~
S
```
Teleport/fiume: `zona flags -1 <time> <target> <mask> [<cnt>] <sector>`, es. `[1, 5071, 3, 10]` (tele_time 1 target 5071 mask 3 -> serve `tele_cnt`).

### 4.2 Mob (`.mob`, 5 varianti di record scelte dalla lettera)

```
#<vnum>
<namelist>~
<short>~
<long>~              (una riga + \n)
<description>~
<act_flags> <affected_flags> <alignment> <LETTERA> [<multi_attack>]
```
Poi, secondo la lettera (`fscanf(" %c ")`, `read_mobile`):

* **`S`** (semplice, 125): `<level> <thac0> <ac> <NdM+K hp> <XdY+Z dmg>`
* **`A N B L`** : `A`, `B`, `L` hanno `<multi_attack>` dopo la lettera (stessa riga; `N` no);
  riga: `<level> <thac0> <ac> <hp_bonus> <XdY+Z dmg>`. Gli hp reali sono `dice(level, 8) + hp_bonus`.
* **`D`** (dettagliato, vecchio Diku; non presente nei dati): 27 interi su 7 righe
  `str int wis dex con / hplo hphi / ac mana move gold exp / position default sex class level age weight height / cond0..2 / save0..4`.

Per `S/A/N/B/L` continua uguale:
```
<gold|-1> [<gold> <exp> <race>  se il primo e' -1 | <exp> altrimenti]
<position> <default_position> <sex_codice> [<immune> <m_immune> <susc> se sex_codice in 3..5]
[solo L: <sound>~ <distant_sound>~]
```
Semantica/unita': `thac0` -> `hitroll = 20 - thac0`; `ac` -> `armor = 10 * ac` (per `S` se |ac| > 10 prima `/10`); `level` 0..61 (dati);
`alignment` -1000..1000; `exp` per `A/N/B/L`: `>= 0` => formula `DetermineExp(mob, exp)`, `< 0` => esperienza fissa `-exp`;
per `S` e' grezza; `race` presente solo con `gold == -1`. `sex_codice`: 0 neutro, 1 maschio, 2 femmina; **3..5 = sesso+3 e seguono 3 maschere**
(immune/m_immune/susc); `>= 6` => neutro senza maschere. `position/default`: 0 DEAD, 1 MORTALLYW, 2 INCAP, 3 STUNNED, 4 SLEEPING, 5 RESTING,
6 SITTING, 7 FIGHTING, 8 STANDING, 9 MOUNTED. Il loader forza `ACT_ISNPC` (8), rimuove `ACT_POLYSELF`/`ACT_SCRIPT`; `B` aggiunge `ACT_HUGE`;
`ACT_SCRIPT` e' assegnato da `scripts.dat`. Se `ACT_SENTINEL` il mob ricorda la stanza di carico.

`act_flags` (bit): 1 NOCHASE, 2 SENTINEL, 4 SCAVENGER, 8 ISNPC, 16 NICE_THIEF, 32 AGGRESSIVE, 64 STAY_ZONE, 128 WIMPY, 256 ANNOYING, 512 HATEFUL,
1024 AFRAID, 2048 IMMORTAL, 4096 HUNTING, 8192 DEADLY, 16384 POLYSELF, 32768 META_AGG, 65536 GUARDIAN, 131072 ILLUSION, 262144 HUGE, 524288 SCRIPT,
1048576 GREET, 2^21 MAGIC_USER, 2^22 WARRIOR, 2^23 CLERIC, 2^24 THIEF, 2^25 DRUID, 2^26 MONK, 2^27 BARBARIAN, 2^28 PALADIN, 2^29 RANGER, 2^30 PSI, 2^31 ARCHER.

`affected_flags` (32 bit): 1 BLIND, 2 INVISIBLE, 4 DETECT_EVIL, 8 DETECT_INVISIBLE, 16 DETECT_MAGIC, 32 SENSE_LIFE, 64 LIFE_PROT, 128 SANCTUARY, 256 DRAGON_RIDE,
512 GROWTH, 1024 CURSE, 2048 FLYING, 4096 POISON, 8192 TREE_TRAVEL, 16384 PARALYSIS, 32768 INFRAVISION, 65536 WATERBREATH, 131072 SLEEP, 262144 TRAVELLING,
524288 SNEAK, 1048576 HIDE, 2097152 SILENCE, 4194304 CHARM, 8388608 FOLLOW, 16777216 PROTECT_FROM_EVIL, 33554432 TRUE_SIGHT, 67108864 SCRYING,
134217728 FIRESHIELD, 268435456 GROUP, 536870912 TELEPATHY.

`immune/m_immune/susc` (bit, `IMM_*`): 1 FIRE, 2 COLD, 4 ELEC, 8 ENERGY, 16 BLUNT, 32 PIERCE, 64 SLASH, 128 ACID, 256 POISON, 512 DRAIN, 1024 SLEEP, 2048 CHARM,
4096 HOLD, 8192 NONMAG, 16384 PLUS1, 32768 PLUS2, 65536 PLUS3, 131072 PLUS4.

`race` (`race.h`): 0 HALFBREED, 1 HUMAN, 2 ELVEN, 3 DWARF, 4 HALFLING, 5 GNOME, 6 REPTILE, 7 SPECIAL, 8 LYCANTH, 9 DRAGON, 10 UNDEAD, 11 ORC, 12 INSECT, 13 ARACHNID,
14 DINOSAUR, 15 FISH, 16 BIRD, 17 GIANT, 18 PREDATOR, 19 PARASITE, 20 SLIME, 21 DEMON, 22 SNAKE, 23 HERBIV, 24 TREE, 25 VEGGIE, 26 ELEMENT, 27 PLANAR, 28 DEVIL,
29 GHOST, 30 GOBLIN, 31 TROLL, 32 VEGMAN, 33 MFLAYER, 34 PRIMATE, 35 ENFAN, 36 DROW, 37 GOLEM, 38 SKEXIE, 39 TROGMAN, 40 PATRYN, 41 LABRAT, 42 SARTAN, 43 TYTAN,
44 SMURF, 45 ROO, 46 HORSE, 47 DRAAGDIM, 48 ASTRAL, 49 GOD, 50-55 GIANT_(HILL,FROST,FIRE,CLOUD,STORM,STONE), 56-65 DRAGON_(RED,BLACK,GREEN,WHITE,BLUE,SILVER,GOLD,BRONZE,COPPER,BRASS),
66-73 UNDEAD_(VAMPIRE,LICH,WIGHT,GHAST,SPECTRE,ZOMBIE,SKELETON,GHOUL), 74 HALF_ELVEN, 75 HALF_OGRE, 76 HALF_ORC, 77 HALF_GIANT, 78 LIZARDMAN, 79 DARK_DWARF, 80 DEEP_GNOME,
81 GNOLL, 82 GOLD_ELF, 83 WILD_ELF, 84 SEA_ELF.

Esempi (inventati, struttura reale):
```
#1
guardia~
La guardia~
Una guardia sorveglia l'ingresso.
~
Una guardia robusta.
~
2097153 0 1000 S
26 1 -10 5d10+550 4d6+3
-1 5000 155 9
8 8 5 0 1 0
```
```
#2
scriba~
Lo scriba~
Uno scriba e' qui.
~
Uno scriba.
~
7 167774240 1000 L 4
50 0 -10 550 5d4+12
-1 100000 6 2
8 8 4 1024 72193 0
Lo scriba dice: Prego controllate se avete posta.~
~
```
(il secondo e' di tipo `L`: due stringhe finali, suono e suono lontano).

Il motore **non verifica** niente: i campi sono letti a ruota con `fscanf` (valori spazzatura su errore). Categorie di record corrotti
che si trovano nei dati reali: dado malformato (`d8+20` senza numero di dadi, `1d4` senza `+K`, `1D5+3`), record troncato (manca la riga
posizione/sesso), stringa senza `~` o con `~` spostata, numero corrotto (`1v5`, `=5`), lettera tipo mancante. L'adapter li espone come record
"raw" ripristinabili.

### 4.3 Oggetto (`.obj`, `objects/<vnum>`)

```
#<vnum>
<namelist>~
<short>~
<long>~              (descrizione a terra)
<action_description>~
<type> <extra_flags> <wear_flags>
<value0> <value1> <value2> <value3>
<weight> <cost> <cost_per_day>        (peso, valore, affitto/giorno)
{ E
  <keywords>~
  <description>~ } *          (tutte le E per prime)
{ A
  <apply_location> <modifier> } *     (max 5; dopo le E)
[ P
  <testo_a_chi_prova>~
  <testo_alla_stanza>~ ]              (messaggio "non puoi indossarlo", opzionale, ultimo)
```
Il loader legge `E*` poi `A*` poi `P`: una `E` dopo una `A` **non viene letta** (e il record successivo e' disallineato); la libreria lo segnala.
Il writer del gioco (`write_obj_to_file`) scrive `P` anche se nei dati e' raro.
Per i file `objects/<vnum>` l'header `#...` e' ignorato (`fscanf("#%*d")`): **nome file = vnum**. Nei file per-vnum l'header puo' non coincidere col nome del file (vale il nome).
`objects/*` scritti dal gioco hanno `\r` nelle stringhe.

`type`: 1 LIGHT, 2 SCROLL, 3 WAND, 4 STAFF, 5 WEAPON, 6 FIREWEAPON, 7 MISSILE, 8 TREASURE, 9 ARMOR, 10 POTION, 11 WORN, 12 OTHER, 13 TRASH, 14 TRAP, 15 CONTAINER,
16 NOTE, 17 DRINKCON, 18 KEY, 19 FOOD, 20 MONEY, 21 PEN, 22 BOAT, 23 AUDIO, 24 BOARD, 25 TREE, 26 ROCK (0 non e' valido). Semantica dei `value[]`
per tipo: `values.doc` (es. ARMOR v0 = AC; WEAPON v1 dadi, v2 facce, v3 tipo colpo 2 whip/3 slash/6 crush/7 pound/11 pierce; CONTAINER v0 peso max, v1 `1 closeable 2 pickproof 4 closed 8 locked`,
v2 vnum chiave; DRINKCON v0 max, v1 attuale, v2 liquido 0..15 (WATER BEER WINE ALE DARKALE WHISKY LEMONADE FIREBRT LOCALSPC SLIME MILK TEA COFFE BLOOD SALTWATER COKE), v3 veleno).
`wear_flags` (bit): 1 TAKE, 2 FINGER, 4 NECK, 8 BODY, 16 HEAD, 32 LEGS, 64 FEET, 128 HANDS, 256 ARMS, 512 SHIELD, 1024 ABOUT, 2048 WAISTE, 4096 WRIST, 8192 WIELD, 16384 HOLD,
32768 THROW, 131072 BACK, 262144 EAR, 524288 EYE (65536 inutilizzato).
`extra_flags` (bit): 1 GLOW, 2 HUM, 4 METAL, 8 MINERAL, 16 ORGANIC, 32 INVISIBLE, 64 MAGIC, 128 NODROP, 256 BLESS, 512 ANTI_GOOD, 1024 ANTI_EVIL, 2048 ANTI_NEUTRAL, 4096 ANTI_CLERIC,
8192 ANTI_MAGE, 16384 ANTI_THIEF, 32768 ANTI_FIGHTER, 65536 BRITTLE, 131072 RESISTANT, 262144 IMMUNE, 524288 ANTI_MEN, 1048576 ANTI_WOMEN, 2097152 ANTI_SUN, 4194304 ANTI_BARBARIAN,
8388608 ANTI_RANGER, 16777216 ANTI_PALADIN, 33554432 ANTI_PSI, 67108864 ANTI_MONK, 134217728 ANTI_DRUID, 268435456 ONLY_CLASS, 536870912 DIG, 1073741824 SCYTHE.
`apply_location` (`A`): 0 NONE, 1 STR, 2 DEX, 3 INT, 4 WIS, 5 CON, 6 CHR, 7 SEX, 8 LEVEL, 9 AGE, 10 CHAR_WEIGHT, 11 CHAR_HEIGHT, 12 MANA, 13 HIT, 14 MOVE, 15 GOLD, 16 EXP, 17 AC, 18 HITROLL,
19 DAMROLL, 20-24 SAVING_(PARA ROD PETRI BREATH SPELL), 25 SAVE_ALL, 26 IMMUNE, 27 SUSC, 28 M_IMMUNE, 29 SPELL, 30 WEAPON_SPELL, 31 EAT_SPELL, 32 BACKSTAB, 33 KICK, 34 SNEAK, 35 HIDE,
36 BASH, 37 PICK, 38 STEAL, 39 TRACK, 40 HITNDAM, 41 SPELLFAIL, 42 ATTACKS, 43 HASTE, 44 SLOW, 45 BV2, 46 FIND_TRAPS, 47 RIDE, 48 RACE_SLAYER, 49 ALIGN_SLAYER, 50 MANA_REGEN, 51 HIT_REGEN,
52 MOVE_REGEN, 53 MOD_THIRST, 54 MOD_HUNGER, 55 MOD_DRUNK, 56-64 T_STR..T_MANA (non implementati). Uno stesso `apply` puo' comparire piu' volte (non e' un dict).

Esempio (inventato, struttura reale):
```
#40001
gile pelle~
Un gile in pelle~
Un gile di pelle nera e' stato lasciato qui.~
~
9 1|16|64|512 1|1024
9 9 0 0
1 30000 0
A
40 5
A
1 3
```

### 4.4 Negozio (`.shp`) - shop.c `boot_the_shops`

```
#<id>~                    (stringa che comincia per '#': l'id e' ignorato)
<prod1> ... <prod5>       5 vnum oggetti prodotti (-1/0 = vuoto)
<profit_buy>              float (moltiplicatore prezzo al giocatore)
<profit_sell>             float
<type1> ... <type5>       5 tipi oggetto trattati (byte)
<no_such_item1>~  <no_such_item2>~  <do_not_buy>~  <missing_cash1>~  <missing_cash2>~  <message_buy>~  <message_sell>~
<temper1> <temper2> <keeper_vnum> <with_who> <shop_room_vnum> <open1> <close1> <open2> <close2>
```
(un intero per riga). `%s` = nome del giocatore, `%d` = prezzo. Ordine **del codice**, non quello di `shops.doc`. Temper1: 0 sputa, 1 fuma; temper2: 0 il mercante colpisce per primo, 1 invulnerabile.
Termina con record `$~`; **un blocco non `#`/non `$` fa girare il loop senza fine**. Nei dati si trovano negozi troncati (meno dei 5 `type`: il motore legge i numeri successivi dalle stringhe) e negozi con `shop_room` inesistente. Esempio: `#40000~ 40002 40003 40001 0 0 1.5 0.5 ... 40000 0 40008 0 24 0 24`.
Il negozio e' agganciato al mob `keeper` (assegna `shop_keeper` come spec proc) e non e' legato alla zona.

### 4.5 Zona e reset (`.zon`)

```
#<znum>
<name>~
<top> <lifespan> <reset_mode>
{ <comando> }*
S
```
`top` = ultimo vnum (inclusivo), `lifespan` in minuti di gioco, `reset_mode` (bit): 0 mai, 1 EMPTY (solo senza giocatori), 2 ALWAYS, 4 ASTRAL (sede del "word of recall"),
8 DESERT, 16 ARCTIC, 32 UNDERGROUND (combinabili).

Comandi (una riga ciascuno: lettera, `if_flag`, argomenti, **commento libero** fino a fine riga). Lettera e argomenti da `boot_zones`:

| Lettera | Significato (reset_zone) |
|---|---|
| `M if mob max room` | carica mob `mob` nella stanza `room` se esistenti `< max` (0 = nessun limite) e nessun combattimento in stanza; imposta il "mob corrente" |
| `C if mob max act_bits` | carica un mob **seguace incantato** (charm) del mob corrente nella sua stanza; `arg3` = bit `act` da aggiungere |
| `O if obj max room max_in_room` | oggetto a terra nella `room` se esistenti `< max` e in stanza `< max_in_room` (0 = illimitato) |
| `P if obj max container` | oggetto dentro un oggetto (`container` = vnum, l'ultima istanza nel mondo) |
| `G if obj max` | oggetto in inventario al mob corrente |
| `E if obj max wear_pos` | oggetto equipaggiato al mob corrente in `wear_pos` (tabella sotto) |
| `D if room dir stato` | stato porta: 0 aperta, 1 chiusa, 2 chiusa+bloccata (forza `EX_ISDOOR`) |
| `H if tipo valore` | odio: `tipo` 1 sesso, 2 razza, 3 (vietato), 4 classe, 5 evil, 6 good, 7 vnum mob (come `OP_*`); un `-1` finale e' solo commento |
| `F if tipo valore` | paura (stessi tipi) |
| `Z if zona 1` | assegna al mob corrente la zona (indice) |
| `*` testo | riga di commento (anche `*M 0 ...` incollato: commento) |
| `S` | fine della tabella della zona |

`if_flag`: nel C e' `int` con regola `esegui se (ultimo comando riuscito) || if_flag <= 0`; quindi **`> 0` = condizionato, `<= 0` = sempre** (valori reali:
`0`, `1`, `-5`, `-39`). Un comando saltato lascia "ultimo riuscito" = falso a catena. `G`/`E`/`H`/`F` non aggiornano il flag (restano riferiti all'ultimo `M`/`C`).
`wear_pos`: 0 LIGHT, 1 FINGER_R, 2 FINGER_L, 3 NECK_1, 4 NECK_2, 5 BODY, 6 HEAD, 7 LEGS, 8 FEET, 9 HANDS, 10 ARMS, 11 SHIELD, 12 ABOUT, 13 WAISTE, 14 WRIST_R, 15 WRIST_L, 16 WIELD,
17 HOLD, 18 BACK, 19 EAR_R, 20 EAR_L, 21 EYES, 22 LOADED_WEAPON.
`R` (documentata in `database.doc`) **non e' implementata** nel loader: nessuna occorrenza nei dati (e `reset_zone` darebbe "Undefd cmd").

Commento: tutto dopo l'ultimo argomento; un editor esterno puo' scrivere commenti lunghi `*! ...` anche **in coda** alla riga di comando; `boot_zones` legge il commento con `fgets(buf, 80)`:
oltre 79 caratteri il resto della riga viene letto come "nuovo comando" con lettera spuria (l'effetto pratico e' perdere righe).

**Trappole del loader C (verificate con un harness che emula il loader)**:
1. `O` richiede **5 numeri** (arg4 `max_in_room`). Nei dati molti comandi `O` ne hanno 4 e il `fscanf(" %d")` per arg4 *salta il newline e fallisce*: la `fgets`
   successiva divora la **riga seguente** (un altro comando oppure la `S` finale della zona). Risultato: il motore vede **meno zone di quelle del file** e meno comandi (zone consecutive fuse, a volte con una zona spuria). Un editor deve **tollerare** arg4 mancante (=0, parser per righe) e **riscrivere sempre 5 numeri** per le `O`.
2. `E` con meno argomenti (1 caso) e le righe `;...`/`*...` valgono come commento solo se sono il primo carattere (nel `zones/<n>.zon` anche `;`).
3. Zone senza `S` finale (capita dopo l'ultima `M`).
4. `dikumoddata4.zon` usa commenti `;!`/`*!` e righe "initlist" senza il nome `~`.

Esempi (inventati, struttura reale):
```
#3
Zona di esempio~
199 20 2
* donation room.
O -5 1 99 99 10
O 0 64 5 167		;rock
M 0 250 5 149
M 0 253 5 152
G 1 3023 100
S
```
```
#4
Altra zona~
249 25 2
M 0 218 10 223   ; una guardia
E 1 3022 47 16   ; una spada lunga
D 0 222 0 1   ; ingresso
```
```
H 1 2 17 -1      (odia la razza 17 GIANT)
F 1 7 3950 -1    (teme il mob vnum 3950)
```

`zones/<n>.zon` (override per-zona): solo comandi fino a `S` (niente header), `LoadZoneFile`, sostituisce la tabella dell'indice n (`atoi(nome)`); non legge arg4 per `O`
(ma `Zwrite` lo scrive): spesso assente.

### 4.6 Altri file formati rilevanti

* `dikumoddata.act` (social, `#`-separati), `dikumoddata.pos` (pose per classe), `dikumoddata.dam` (messaggi di combattimento, stringhe con `~`): non parte del mondo editabile, grammatica Diku classica.
* `credits`, `motd`, `help`, `helptbl`, `whelptbl`, `info`: testo.

## 5. Script dei mob (`scripts.dat`, `scripts/<Nome>`)

`scripts.dat`: una riga per script `Nome vnum_mob` (es. `Banker 3078`). `scripts/<Nome>`: una riga per istruzione, eseguita
una per pulsazione; la prima parola e' o un'istruzione del linguaggio o un comando del MUD (`say`, `emote`, `bow`...):

| Istruzione | Effetto |
|---|---|
| `noop N` | attende N pulsazioni (0/assente: una) |
| `goto <room>` / `goto $nome` | va alla stanza o verso il personaggio |
| `jsr <label>` / `jmp <label>` / `rts` | sottoprogramma / salto / ritorno; la label e' un prefisso di riga |
| `act <bits>` | imposta i flag `act` del mob |
| `end` / `stop` | ricomincia da capo (indice 0) |
| riga che finisce con `\` | esegue anche la riga seguente nello stesso tick; riga che inizia con `_` avanza di una |
| qualunque altro | passata al `command_interpreter` |

L'associazione script <-> mob e' **solo** in `scripts.dat` (ACT_SCRIPT calcolato a runtime). Nessun campo nel `.mob`.

## 6. Gilde (`dikumoddata.gui`, `gilde/`)

`dikumoddata.gui`: una riga per gilda: `<BaseName> <guardia_mob> <stanza_guardia> <direzione> <banchiere_mob> <stanza_banca> <banchiere_xp_mob> <stanza_banca_xp> <libro_soci_obj>`;
es. `NomeGilda 3146 3164 3 3149 3166 3147 3170 40021`. `gilde/<Base>.member` (un nome per riga, il primo e' il capogilda) e `<Base>.exp.tot`. Il `gui~` ha la riga spezzata su piu' righe (versione di lavoro).
Le stanze della gilda hanno il flag `SAVE_ROOM` (8192, vedi `world/<vnum>` binari) e i mob/oggetti vanno comunque messi con `M`/`O` in `.zon`.

## 7. Irregolarita' e pitfall (riassunto, con categorie di fallimento)

Categorie di irregolarita' osservate nei file principali:

| File | Irregolarita' |
|---|---|
| `dikumoddata.wld` | possibile stanza con campi corrotti ma "parsabile" (es. `~` spostata: una riga numerica finisce nella descrizione e il settore diventa un numero enorme) |
| `dikumoddata.mob` | dado malformato, record troncato, numero corrotto, `~` mancante/extra, lettera tipo mancante |
| `dikumoddata3.mob` | in piu': record troncati (exp/race persi dall'export) |
| `dikumoddata.obj` | vnum duplicati |
| `dikumoddata.zon` | comandi `O` senza arg4, `E` troncata, zona senza `S`; il **loader C** perde alcune zone (v. 4.5) |
| `dikumoddata.shp` | negozio troncato (meno dei 5 `type`) |
| `rooms/*`, `objects/*` | override validi; file di backup `*~` da ignorare |

Altre insidie:

* **Duplicati**: vnum mob/oggetto ripetuti (v. sez. 3); `zone #N` ripetuti. Un editor non puo' usare `#N` come chiave di zona.
* **Mob = due oggetti in uno**: la sintassi del record cambia con la lettera (5 varianti) e col codice sesso (3..5 -> 3 numeri extra) e con `gold == -1` (3 numeri) e `L` (2 stringhe):
  la lunghezza del record e' variabile e dipende da campi precedenti.
* **Flag sommati con `|`**: `fread_number` somma. Scrivere sempre un solo intero (o bit unici); l'editor Windows scrive `a|b|c`.
* **File principale monolitico**: `.wld`, `.mob`, `.obj`, `.zon` possono pesare da centinaia di KB a oltre un MB. `.mob/.obj` sono letti per **offset di byte** a runtime: modificare un
  file con il gioco acceso lo rompe; riscrivere l'intero file con rename atomico e riavviare/`reload`.
* **Override per-vnum**: l'ordine di precedenza e' `rooms/<v>` > `dikumoddata.wld`, `objects/<v>` > `dikumoddata.obj`, `zones/<n>.zon` > comandi di `dikumoddata.zon`. Un adapter che modifica solo il file principale
  e dimentica l'override produce modifiche "invisibili" (e viceversa). Il nome file e' l'identita' (header ignorato).
* **Header di stanza/oggetto non affidabile** nei file per-vnum (puo' non coincidere col nome del file).
* **`RoomSave`** scrive il blocco fiume solo per `SECT_WATER_NOSWIM` (non per UNDERWATER) e omette `L`: un round-trip tramite il codice del gioco perde dati.
* **Doc obsoleti**: `database.doc` (formato zon/room base) e la documentazione `dbsup` (door flag 0-7, no flag oltre 8192) sono piu' vecchi del codice; usare le tabelle di questo documento.
* **Encoding**: ASCII; gli unici non-ASCII sono nel log `dikumoddata.err` (CP1252).

## 8. Implicazioni per gli adapter

### (a) Quanto entra nel modello neutro (`common/adapters/models.py`)

| Entita' | Nel nucleo | In `extra` / da estendere |
|---|---|---|
| Zona | `name`, `top_vnum`, `bottom_vnum` (derivato), `lifespan_minutes`, `reset_mode` (0 NEVER, 1 EMPTY, 2 ALWAYS), `enabled=true`, `builder=""`, `min/maxLevel=1` | `numRaw` (`#N`), `resetModeRaw` (bit 4/8/16/32), `index`; `id`/`vnum` = **indice di posizione** (non `#N`, non univoco) |
| Stanza | `vnum`, `name`, `description`, `sector_type` (0-12 + mappa su enum pachimud, `extra.sector` autoritativo), `flags` (nomi 26 bit), `zone_id` (da range) | `tele{time,target,mask,count}`, `river{speed,dir}`, `moblim`, `lightNight/lightDay` (`L`), `zoneIgnored`; `heal/manaRate`, `clanId`, `owner` non esistono (valori neutri) |
| Uscita | `direction` 0-5, `description`, `keywords`, `key_vnum`, `target_room_vnum`; `door_flag` = NONE/CLOSABLE/PICKPROOF da bit `ISDOOR/PICKPROOF`; `is_open/is_locked` dai bit CLOSED/LOCKED + reset `D` | `exitInfo` grezzo (SECRET NOTBASH CLIMB MALE NOLOOKT NOKNOCK INVIS), `openCmd` |
| Extra descr | `keywords`, `text` | - |
| Mob | `keywords`, descrizioni, `level`, `thac0 = 20 - file`, `armor_class`, `hp_*`/`damage_*` dadi (A/N/B/L: `hp = level d8 + bonus`), `gold`, `experience`, `sex`, `flags` (31 bit ACT), `alignment`, `race_id` (0-84) | `kind` (S/A/N/B/L/D), `multiAttack`, `affectedBy`, `position`, `defaultPos`, `immune/mImmune/susc`, `sound/distantSound`, `expRaw`, `shop` (da `.shp`), `script` (da `scripts.dat`), `guild`; `class/debuff/quest/banker/teaches*` neutri |
| Oggetto | `keywords`, `short`, `long`, `action_description`, `object_type` (1-26; 0 -> OTHER), `weight`, `cost`, `rent = cost_per_day`, `value_0..3`, `extra_flags`, `wear_flags` | `affects` come **lista** (stesso apply ripetuto; il `dict[str,int]` neutro li somma e perde l'ordine), `extraDescs`, `forbiddenWear{toChar,toRoom}` (`P`) |
| Reset | M, O, G, E, P, D con `arg1..arg4`/`argStr` | `if_flag` intero (`>0` condizionato, ma esistono `-5`, `-39`), `comment` (non esiste nel DTO), `C` (charm), `H`/`F` (hate/fear), `Z`, `R` (non implementato) |

Il grosso e' mappabile; le perdite sono tutte recuperabili con `extra` **a patto di preservare il testo** non toccato (come fa BasedMud con `preserve=True`).

### (b) Descrivibile in modo dichiarativo (YAML) o con hook in codice

Dichiarativo (grammatica + mapping): sequenze di campi tipizzati (`string~`, `int`, `flags` con `|`, `dice NdM+K`), blocchi **condizionali su un campo
gia' letto** (`sector == -1`, `tele_mask & 2`, `sector in {7,9}`, `room_flags & 256`, `gold == -1`, `sex in 3..5`, lettera `S/A/B/L/N`), liste di sezioni con
tag (`D<n>`, `E`, `L`, `C`, `A`, `P`) terminate da sentinella (`S`, `%%`, `$~`), terminatori diversi per file, tabelle bit -> nome, lettere di comando con numero di argomenti per lettera,
un file monolitico con record separati da `#vnum` (indicizzazione per offset facoltativa). Queste regole coprono `.wld`, `.mob`, `.obj`, `.zon`, `.shp`, i file per-vnum e `dikumoddata.gui`.

Hook di codice necessari (non banali da esprimere in YAML):
1. **Calcolo zona dal vnum** per intervallo (`top`) e zone senza identita' propria (id = indice; `#N` duplicati).
2. **Trasformazioni semantiche**: `thac0 = 20 - x`, `AC * 10` e regola `|ac| > 10 -> /10` per `S`, `hp = level d8 + bonus` per A/N/B/L, `exp` con formula/negativo, sesso 0-5 + maschere, `if_flag` -> bool + cattura del residuo.
3. **Join tra file**: negozio per `keeper`, script per vnum (`scripts.dat`), gilda, override `rooms/` `objects/` `zones/`; precedenza e riscrittura nel posto giusto.
4. **Loader tollerante che emula `fscanf`** (arg4 mancante, commenti lunghi, record troncati) con **diagnostica** per record (numero di riga, categoria) invece di eccezione: alcuni mob non sono parsabili e devono restare visibili/ripristinabili come "raw".
5. **Writer a conservazione byte** (record non toccati identici) e atomico; riscrivere sempre `O` con 5 numeri; non emettere `|` salvo conservazione; gestione `\r` interni.
6. **Regole di integrita'** specifiche: chiavi uscite (`key` oggetto), stanze/mob/oggetti dei reset, negozi/gilde/script che puntano a un vnum, unicita' dei vnum (assente nel motore: duplicati reali).
7. Il **flusso di reset a catena** (M/G/E/H/F sul mob corrente, `if_flag` sul comando precedente) per `validate_reset_commands`.

### (c) Modifiche necessarie a interfaccia e [adapter](../adapters/sdk.md)

* **`id` di zona**: documentare che per i MUD senza area.lst e con `#N` non univoco `id` = indice di posizione (come BasedMud usa `-posizione`), e che `bottom_vnum` e' derivato dal `top` della precedente: un
  cambio di `top` sposta le stanze fra zone (serve un controllo e un'anteprima: `range_clash`/`check_zone_ranges` partono da bottom *e* top espliciti, qui bottom e' derivato).
* **`ResetCommandOut/In`**: aggiungere `comment: str | None`, `if_flag` come intero (o `raw_if_flag` in `extra`) e nuovi `ZoneCommandType` (`CHARM_MOB`, `SET_HATE`, `SET_FEAR`; opzionale `SET_MOB_ZONE`) oppure un meccanismo di `extra` per comando.
  Le validazioni di `rules.py` assumono i 7 tipi ROM: devono diventare dipendenti dal mondo (`USAGE_FIELDS` per `C`, `H` col vnum mob solo per tipo 7).
* **Entita' non neutre**: negozi, script mob e gilde non hanno DTO; proporre `extra.shop` (come BasedMud), una capability `supports_shops/scripts` oppure risorse aggiuntive in `describe()` (gia' previsto `resources[]`).
* **Flag/enum per mondo**: `enums()` deve poter restituire tabelle diverse da ROM (`dikumodRoomFlags`, `dikumodActFlags`, `dikumodAffectFlags`, `dikumodExtraFlags`, `dikumodWearFlags`, `dikumodApplyTypes`, `dikumodRaces`, `dikumodImmunity`, `dikumodWearPos`); i DTO usano `list[str]` quindi basta.
* **Override per-vnum**: aggiungere in `describe()` o nel `world` config una politica (`write_target: main|override`) e documentare nell'adapter che `read_only` si applica a tutti i file; `mtime/size` della cache va esteso alle cartelle override.
* **Diagnostica di caricamento**: un endpoint o un campo `issues` per i record non parsabili (mob corrotti, negozio troncato, `O` senza arg4, zona senza `S`), oggi non previsto (gli errori sono solo di scrittura).
* **Export/ripristino**: file monolitici da centinaia di KB: bisogna dichiarare nel contratto che una scrittura riscrive un file intero (lock singolo per adapter, come BasedMud).
* **Adapter `mapping` generico**: il YAML deve prevedere (i) `files` con ruolo e terminatori, (ii) `records` con grammatica a campi + condizioni, (iii) `tables` bit->nome, (iv) `joins`/`overrides`, (v) `hooks` Python registrabili per le trasformazioni di (b).

### (d) La base e' Diku classico? Altri MUD?

Si': `.wld/.mob/.obj/.zon/.shp` sono il DikuMUD classico (record `#vnum`, stringhe `~`, stanze `S`, uscite `D<n>`, extra `E`, mob `S/D`, oggetti `E/A`,
zona `M O G E P D`). Le **estensioni del Diku Modificato** sono: mob `A B L N` + `multi_attack` + suono, sesso con maschere, race con `-1`;
flag con `|`; stanze con `-1` (teleport), fiume, tunnel, `L`/`C`; oggetti `P`; reset `C H F Z` + `arg4` per `O`; `rooms/ objects/ zones/` per-vnum;
script e gilde. Quindi un mapping "Diku generico" parametrizzato (set di lettere, blocchi condizionali, tabelle) puo' servire per DikuMUD/merc/SillyMUD e,
con un dialetto diverso, per tbaMUD/Circle (flag come lettere a-z `asciiflag`, `E` per i mob, zona con header builder, `D if room dir state` ma lettere/semantica diverse e `.zon` con `T/V`).
Il mapping `diku_classic.yaml` e' proprio questo: una grammatica YAML generica, mentre l'adapter `dikumod` e' dedicato (override, script, gilde, record corrotti).

DikuMUD II ha un **formato completamente diverso** e non riconducibile alla stessa grammatica: i dati sono sorgenti `.zon` testuali con direttive
`%zone/%rooms/%mobiles/%objects/%reset`, macro del preprocessore C, campi nominali e programmi DIL, compilati in file binari. Non serve il mapping Diku classico:
richiederebbe un parser dedicato.
