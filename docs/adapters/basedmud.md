# Adapter BasedMud (`kind: basedmud`, file `.are` ROM/QuickMUD)

Legge e scrive i file area di basedmud con `adapters/basedmud/src/pachimudeditor_adapter_basedmud/rom_lib` (vedi il suo README): ogni scrittura riscrive **solo
il file toccato**, in modo atomico e con `preserve=True` (gli elementi non modificati restano byte per byte).

```yaml
webeditor_worlds:
  - {id: pachimud, kind: pachimud, name: Pachimud}
  - {id: basedmud, kind: basedmud, name: BasedMud, path: /percorso/basedmud, read_only: false}
```

`path` = radice di basedmud o la sua cartella `area/` (con `area.lst`). Lo stesso `path` in due mondi (uno `read_only`) e'
ammesso. Cache dei file invalidata da `(mtime, size)` + `area.lst`: modifiche esterne sono viste alla richiesta dopo.
Un solo `asyncio.Lock` per adapter serializza le scritture (non per file: una scrittura puo' toccare piu' file, es.
uscite entranti o spostamento tra zone).

## Convenzioni di `id`

| Risorsa | `id` | Note |
|---|---|---|
| zona | vnum minimo dell'area (`== vnum == bottomVnum`) | area senza range numerico univoco (`0 0`, `XX00 XX99`, doppioni): `-(posizione tra le zone)`. Cambiare `bottomVnum` cambia l'`id` |
| stanza, mob, oggetto | `vnum` | univoco in tutto il mondo; `zoneId` = id della zona del file che lo contiene |
| uscita | `vnum_stanza * 10 + direzione` | `roomId` = vnum |
| extra description di stanza | `vnum_stanza * 1000 + posizione` | togliere una voce fa scalare le successive |
| comando di reset | posizione nello script (righe `*` escluse) = `orderIndex` | |

Zone = file `.are` con intestazione (`#AREA`/`#AREADATA`); i file di soli help/social (`help.are`, `social.are`, `olc.hlp`)
sono ignorati. `enabled` = il file e' in `area.lst`: i `.are` presenti in cartella ma non elencati (es. `proto.are`) sono
zone `enabled: false`; `enabled: false/true` toglie/mette la riga in `area.lst` (il `$` finale resta). Creare una zona
scrive `<slug>.are` (o `extra.file`) + riga in `area.lst`; eliminarla (solo se vuota) cancella il file e la riga.

## Mapping nel nucleo e in `extra`

- **Zona**: `name`, `builder` (`Builders` o autore nei credits), `bottom/topVnum`, `min/maxLevel` (blocco `{ min max }` dei
  credits, altrimenti 1-60), `enabled`. `lifespanMinutes`=15 e `resetMode`=EMPTY sono costanti (ROM non ha il campo: il
  patch e' ignorato). `extra`: `file`, `style`, `vnumRaw` (sola lettura), `credits`, `security`.
- **Stanza**: nome, descrizione, `flags` (nomi di `room_flags`), `healRate`, `manaRate`, `clanId`, `owner`. `sectorType` e'
  l'approssimazione sulla enum pachimud (8 `unused`->UNDERWATER, 9 air->FLYING, 10 desert->FIELD); `extra.sector` e' il
  settore ROM vero (0-10) e prevale se inviato. Uscite: `doorFlag` NONE/CLOSABLE/PICKPROOF da `locks` (nopass non e' nel
  DTO ma viene conservato); `keyVnum` (<=0 = nessuna); `isOpen`/`isLocked` sono lo stato del reset `D` della stanza
  (nessun `D` = aperta) e vengono scritti li' (creare/modificare/eliminare l'uscita aggiorna il `D`);
  `targetRoomId` e' null se la destinazione non esiste (`targetRoomVnum` ha comunque il valore del file).
- **Mob**: `keywords`=name, descrizioni, `level`, `flags`=act, `raceId`=razza ROM (vuota=null), `alignment`, `gold`=wealth,
  `sex` (none->NEUTRAL, either->BOTH), dadi hp/danno = `hit`/`damage`, `thac0 = 20 - hitroll`, `armorClass` = AC pierce
  (`ac[0]`). `extra`: `affectedBy offFlags immFlags resFlags vulnFlags form parts` (liste di nomi), `size material startPos
  defaultPos group damType`, `mana` ("NdT+B"), `ac` (4 valori), `flagRemovals` (righe `F`, `{word, value}`), `mprogs`
  (righe `M`), `shop` (voce `#SHOPS` o null), `special` (spec_fun di `#SPECIALS` o null). Campi senza equivalente
  (`experience`, `classId`, `debuffSkillId`, `shopId`, `questIds`, `isBanker`, `teaches*`) si leggono neutri e in scrittura
  accettano solo il valore neutro (422 `basedmud.field_unsupported`). Un mob nuovo riceve sempre il flag `npc`.
- **Oggetto**: keywords/short/long, `objectType` (tipi ROM non pachimud -> OTHER), `weight`, `cost`, `extraFlags`,
  `wearFlags`, `valueN` (int; null se lo slot contiene un nome, es. liquido/skill), `affects` (solo righe `A`, nome apply ->
  somma). `rent` e `actionDescription` non esistono (solo valore neutro). `extra`: `itemType` (tipo ROM vero), `values`
  (v0-v4 grezzi), `level`, `material`, `condition`, `flagAffects` (righe `F`), `extraDescs`.
- **Reset** (come pachimud): M `arg1` mob, `arg2` max globale, `arg3` stanza, `arg4` max in stanza; O oggetto/max/stanza;
  P oggetto/max/contenitore + `arg4` quantita'; G oggetto/max; E come G + `argStr` slot (`wear_loc_types`: `wielded`...);
  D stanza/direzione + `argStr` OPEN/CLOSED/LOCKED; R stanza + `arg2` numero di direzioni. Il limite `-1` (nessun limite)
  e' `arg2 = null` per G/E/P e 0 per O. Sostituire lo script riusa i reset invariati (stessi byte e commenti); le righe
  `*` si perdono solo se lo script cambia.
- Un patch applica solo i campi **diversi** dal valore corrente: rimandare il DTO letto (`extra` compreso) non cambia i byte.
  Chiavi di `extra` sconosciute: 422 `basedmud.extra_unknown`; flag sconosciuti: 422 `basedmud.unknown_flag`.

## Integrita'

Vnum univoci nel mondo (409 `*.vnum_taken`) e nel range della zona se ne ha uno (422 `basedmud.vnum_out_of_range`, anche
per spostamenti tra zone con `zoneId`); cambio vnum/eliminazione bloccati se usati da reset (`*.vnum_in_use`,
`*.in_reset_usage`, oggetti anche come chiave di uscita: `objects.in_exit_key_usage`); il cambio vnum di una stanza
aggiorna le uscite che la raggiungono e i suoi `D`, eliminarla azzera le uscite entranti e toglie i suoi `D`; negozio e
spec_fun di un mob seguono vnum/zona e vanno via con lui; validazione dei reset con `rules.validate_script` (lookup sui
file); range zone con `rules.check_zone_ranges/range_clash`. Nomi di file: solo `[A-Za-z0-9_.-]+.are`, mai separatori
(422 `basedmud.invalid_file_name`).

## Meta e capability

`enums()` = le sette enum standard dei DTO + tabelle ROM (`romRoomFlags`, `romMobFlags`, `romAffectFlags`, `romOffFlags`,
`romResFlags`, `romFormFlags`, `romPartFlags`, `romExtraFlags`, `romWearFlags`, `romSectorType`, `romItemType`, `romWearLoc`,
...: per i flag `value` e' il bit, per i tipi l'indice). `races()`/`classes()` leggono `race_table`/`class_table` da
`<radice>/src/tables.c` (vuote se manca). Capability: solo `supportsResetScripts` e `supportsExtraDescriptions`.

## Limiti noti

Niente `#MOBPROGS`/`#HELPS`/`#SOCIALS` modificabili (solo conservati); `experience`, classi, quest non esistono; `thac0` e
`armorClass` sono viste di `hitroll` e `ac[0]`; il codice porta nopass non e' esposto; `id` di zone senza range e di
uscite/extra cambiano con la struttura; nessuna transazione tra piu' file (uno spostamento scrive prima la destinazione);
modifiche esterne contemporanee non sono rilevate fino alla scrittura successiva.
