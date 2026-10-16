# rom_lib (pachimudeditor_adapter_basedmud.rom_lib)

Libreria Python standalone (solo stdlib, nessun import di pachimud) per leggere e scrivere i file
area `.are` di ROM 2.4 / QuickMUD / basedmud. Fonte di verita' del formato: `db.c` (`load_*`) e
`olc_save.c` (`save_*`) di `/percorso/a/basedmud/src`.

```python
from pachimudeditor_adapter_basedmud.rom_lib import load_area_file, save_area_file, add_area_to_list

area = load_area_file("area/midgaard.are")        # RomParseError con riga/colonna se malformato
area.find_mobile(3000).level = 30
save_area_file("/tmp/midgaard.are", area)         # atomico (temp + os.replace), newline e `#$` conservati
add_area_to_list("/tmp/area.lst", "midgaard.are") # mantiene il terminatore `$`
```

## Modello (`model.py`)

- `Area`: `sections` (ordine del file) + scorciatoie `header`, `mobiles`, `objects`, `rooms`, `resets`,
  `shops`, `specials`, `mobprogs`, `helps`, `socials`, `find_mobile/object/room(vnum)`; `newline`, `encoding`.
  L'accesso a una scorciatoia crea la sezione se manca (se resta vuota non viene scritta).
- `AreaHeader`: `#AREA` (vecchio: filename/name/credits/vnum) e `#AREADATA` (Name/Builders/VNUMs/Credits/Security).
  `style` seleziona il formato in scrittura; `vnum_raw` conserva range non numerici (proto.are: `XX00 XX99`).
- `Room` (+ `Exit`, `ExtraDescription`): flag, settore, uscite (`locks` 0-4 come nel file, key, to_vnum),
  `heal_rate`/`mana_rate` (default 100), `clan`, `owner`.
- `Mobile` (+ `Dice`, `FlagRemoval` per le righe `F`, `MobProgTrigger` per le righe `M`): tutti i campi ROM,
  flag `act/affected_by/off/imm/res/vuln/form/parts` come interi, `ac` = i 4 valori del file.
- `Object` (+ `ObjectAffect` per `A`/`F`, `ExtraDescription` per `E`): `values` = 5 stringhe v0-v4 (grezze,
  senza apici), `named_values()`/`set_named()` per tipo (weapon, container, drink, fountain, wand, staff,
  potion, pill, scroll), `value_int(i)`; `condition` = lettera P/G/A/W/D/B/R.
- `Reset` (`command` M O P G E D R, `args` come nel loader, `comment`; `named()/get()/set()/Reset.make()`),
  `Shop`, `Special`, `MobProg`, `Help`, `Social`, `CommentLine` (righe `*` in #RESETS/#SPECIALS).
- Sezioni sconosciute (es. `#MOBOLD`, `#OBJOLD`): `Section(kind="RAW", name, text)` riemesse identiche.

## Sezioni supportate

`#AREA`, `#AREADATA`, `#MOBILES`, `#OBJECTS`, `#ROOMS`, `#RESETS`, `#SHOPS`, `#SPECIALS`, `#MOBPROGS`,
`#HELPS`, `#SOCIALS`, terminatore `#$` (e testo successivo, conservato).

## Fedelta' di scrittura

Ogni elemento parsato ricorda il proprio testo sorgente e un'impronta dei campi. `write_area(area)`:

- elementi **invariati**: testo originale riemesso byte per byte (anche testate/terminatori di sezione);
- elementi **nuovi o modificati**: formato canonico di `olc_save.c` (`save_mobile`, `save_room`, ...);
- `write_area(area, preserve=False)`: tutto il file rigenerato in forma canonica (idempotente).

Le stringhe usano `\n` nel modello; in scrittura `area.newline` (`\n` o `\r\n`, rilevato al parsing) e'
applicato al testo canonico. L'encoding e' UTF-8 se valido, altrimenti latin-1 (lossless).

## Flag (`flags.py`)

`parse_flags("ABV|16") -> int` (come `fread_flag`), `format_flags(v)` (come `fwrite_flag`: `"0"` o lettere
crescenti A-Z, a-z), `flags_to_letters`, `letters_to_flags`, `has_flag`, `set_flag`, `flag_names(tabella, v)`,
`names_to_flags(tabella, nomi)`. Le tabelle (`tables.py`: `FLAG_TABLES`, `TYPE_TABLES`) sono estratte da
`basedmud/json/meta`; i bit sconosciuti compaiono come `[X]`.

## Errori

`RomParseError(message, line, column, context, filename)` (sottoclasse di `ValueError`), es.
`midgaard.are: riga 120, colonna 8 [MOBILES vnum 3000]: numero atteso`. `RomWriteError` per dati non serializzabili.

## Differenze dal saver C (volute)

- I valori v0-v4 degli oggetti sono scritti cosi' come sono (il C converte i tipi "default" con `fwrite_flag`,
  trasformando `10` in `BD` e `-1` in tutte le lettere); le skill/liquidi sono tra apici come in `save_object`.
- Gli elementi sono scritti nell'ordine della lista (il C itera per vnum/hash); uscite, extra desc, H/M di
  stanza e F/M di mob mantengono l'ordine del modello.
- I commenti dei reset/shop/special sono un campo (`comment`) e non vengono rigenerati dai nomi.
- `fix_string` come in C: `~` e `\r` sono rimossi dalle stringhe scritte.

## Lacune note

- Nessuna validazione semantica (vnum duplicati, riferimenti inesistenti, razze/skill/spec sconosciute).
- Non interpreta `#MOBOLD`/`#OBJOLD` (formato vecchio): conservati come RAW.
- Le chiavi sconosciute di `#AREADATA` sono conservate come testo di riga (valori su piu' righe non supportati).
- Le lettere flag arrivano fino al bit 51 (`z`); valori negativi si scrivono in decimale.
- Reset `D` non applicati alle uscite (come nel C sono solo istruzioni); nessuna ricostruzione di `rs_flags`.
- Un file `.are` e' interpretato per intero in memoria (nessuno streaming).

## Test

`uv run pytest tests/rom_lib -q` (con `-s` stampa le statistiche del round trip sulle aree
reali di basedmud; `ROM_AREA_DIR` per cambiare cartella; si lavora su una copia temporanea).
