# Adapter Diku Modificato (`kind: dikumod`)

Legge e scrive i file dati di Diku Modificato (un Diku molto modificato) con `adapters/dikumod/src/pachimudeditor_adapter_dikumod/dikumod_lib` (vedi il suo README e
[formato Diku Modificato](../formats/dikumod.md), scritto leggendo il caricatore del gioco).

```yaml
webeditor_worlds:
  - {id: dikumod2, kind: dikumod, name: "Diku Modificato", path: /percorso/dikumod2, params: {variant: dikumod2}}     # sola lettura
  - {id: dikumod2-rw, kind: dikumod, path: /percorso/dikumod2/lib, read_only: false}                            # scrittura abilitata
```

**Diku Modificato o `diku_classic`?** Esistono due modi di leggere un Diku: questo adapter dedicato (`kind: dikumod`: override per-vnum,
script, gilde, record corrotti ripristinabili, scrittura a conservazione di byte) e l'esempio `diku_classic.yaml` del
[mapping generico](mapping.md) (`kind: mapping`: il Diku classico "un file per tipo" descritto in YAML, senza questi extra).

Il **prefisso dei file dati** e' `dikumoddata` (`dikumoddata.wld`, `.mob`, `.obj`, `.zon`, `.shp`, `.gui`) e si cambia con `params.data_prefix`
(facoltativo; solo lettere, cifre, `_` e `-`, nessun percorso):

```yaml
  - {id: miomondo, kind: dikumod, path: /percorso/miomondo/lib, params: {data_prefix: miomondo}}   # miomondo.wld, miomondo.mob, ...
```

Se i file non si trovano l'errore e' `nessun file <prefisso>.wld in <cartella>: imposta params.data_prefix`.

`path` = la cartella `lib/` (con `dikumoddata.wld`) o la sua radice. `params.variant` (`dikumod`|`dikumod2`) e' facoltativo e
informativo (se manca: `dikumod2` quando esistono `dikumoddata.gui` o override `rooms/`).

**`read_only` vale `true` se non e' scritto** (unico kind con questo default; `read_only: false` e' l'abilitazione esplicita).
Motivo: i file monolitici sono fragili. `dikumoddata.mob`/`.obj` sono letti dal gioco **per offset di byte** raccolti all'avvio
(`generate_indices`) e cercati con una ricerca **binaria**: modificarli a gioco acceso lo rompe, e un file non in ordine di
vnum o senza `%%` finale fa fallire il caricamento. Una scrittura riscrive per intero il file toccato (1,4 MB il `.wld`) in
modo atomico (temporaneo + `os.replace`), con **un solo `asyncio.Lock`** per adapter (una scrittura puo' toccare piu' file:
uscite entranti, negozio, script) e cache per file invalidata da `(mtime, size)`; gli elementi non toccati restano byte per
byte. Fermare il gioco, scrivere, riavviare.

## Convenzioni di `id`

| Risorsa | `id` | Note |
|---|---|---|
| zona | **posizione** nel `dikumoddata.zon` (`id == vnum == indice`) | il numero `#N` non e' univoco (138 e 151 doppi): e' in `extra.numRaw`. Eliminare una zona fa scalare gli id successivi |
| stanza, mob, oggetto | `vnum` | `zoneId` e' **derivato**: la prima zona con `top >= vnum` (un `zoneId` diverso nel body e' 422 `dikumod.zone_derived`) |
| uscita | `vnum_stanza * 10 + direzione` | |
| extra description di stanza | `vnum_stanza * 1000 + posizione` | togliere una voce fa scalare le successive |
| comando di reset | posizione tra i comandi (commenti e righe vuote esclusi) = `orderIndex` | |

Range di zona: una zona ha solo `top`; `bottomVnum` e' **derivato** (`top` della precedente + 1; 0 per la prima). Una zona
che non possiede vnum (suo `top` uguale a quello della precedente) mostra `0-0`. Quindi `bottomVnum` non e' modificabile (422
`dikumod.zone_bottom_derived`), cambiare `topVnum` sposterebbe contenuto fra zone vicine (409 `dikumod.zone_range_has_content` se c'e'
contenuto nell'intervallo, 422 `dikumod.zone_top_order` se esce dall'ordine dei `top`) e **una zona nuova si aggiunge in coda**
(`bottomVnum` deve essere `top` dell'ultima + 1; senza range nasce vuota). `next_zone_vnum` restituisce `(vnum = numero di zone,
bottom = top dell'ultima + 1)`.

Precedenza dei file per-vnum (in lettura **e in scrittura**): `rooms/<vnum>` > `dikumoddata.wld`, `objects/<vnum>` > `dikumoddata.obj`,
`zones/<n>.zon` > comandi di `dikumoddata.zon` (l'indice `n` e' quello di posizione). Il nome del file e' l'identita' (l'header `#N`
e' ignorato, in `objects/40022` e' `#3099`). Un'entita' con file per-vnum non cambia vnum (422 `dikumod.override_vnum_locked`);
eliminarla toglie anche il file. Nomi non interamente numerici (`40033~`) sono ignorati. Vnum doppi nei file (stanza 6542, mob
3703 16053 19208 21356, oggetti 16056 16207 21361): l'API ne mostra uno (stanza: l'ultimo come il loader; mob/oggetti: il primo)
con `extra.warning`.

## Mapping nel nucleo e in `extra`

- **Zona**: `name`, `topVnum`, `bottomVnum` (derivato), `lifespanMinutes`, `resetMode` (bit 2 -> ALWAYS, bit 1 -> EMPTY, altrimenti
  NEVER). Neutri e **ignorati in scrittura**: `builder` (""), `minLevel`/`maxLevel` (1), `enabled` (sempre `true`: Diku Modificato non ha il
  concetto). `extra`: `numRaw` (`#N`, scrivibile), `resetModeRaw` (bit 4/8/16/32 compresi, scrivibile), `index`, `topRaw`, `hasEnd`
  (manca la `S` finale: la riscrittura la aggiunge), `override` (nome di `zones/<n>.zon`).
- **Stanza**: nome, descrizione, `flags` (26 bit, nomi `dikumodRoomFlags`), `sectorType` approssimato (8 aria -> FLYING, 10/11/12 ->
  FIELD/FOREST/CITY), `healRate`/`manaRate`/`clanId`/`owner` neutri (valori diversi: 422 `dikumod.field_unsupported`). `extra`: `sector`
  (settore vero 0-12, autoritativo), `tele {time,target,mask,count}`, `river {speed,dir}` (scritto solo con settore 7 o 9), `moblim`
  (solo con flag `tunnel`), `light {night,day}` (blocco `L`), `zoneIgnored`, `source` (`main`/`override`).
  **Uscite**: `doorFlag` NONE/CLOSABLE/PICKPROOF da `ISDOOR`/`PICKPROOF`; `keyVnum` (`<= 0` = nessuna: il valore `0` e' "senza
  chiave" in 1587 uscite); `isOpen`/`isLocked` dal comando `D` della zona se c'e', altrimenti dai bit `CLOSED`/`LOCKED` (la scrittura
  aggiorna i bit **e** i `D` esistenti; il reset forza `ISDOOR`); `targetRoomId` e' null se la stanza non esiste. `extra`: `exitInfo`
  (bit grezzi: secret, notbash, climb, male, nolookt, noknock, invis...), `openCmd`, `dState`.
- **Mob**: `keywords`, descrizioni, `level`, `flags` (32 bit `act`), `alignment`, `gold`, `sex` (0 neutro, 1 maschio, 2 femmina;
  `Sex.BOTH` non esiste: 422), `raceId` (nome minuscolo della tabella `race.h`; `null` = il mob non ha il campo razza), `thac0` e
  `armorClass` = i valori del file (nel gioco `hitroll = 20 - thac0`, `armor = 10 * ac`), `damage*` = `XdY+Z`, hp: tipo `S` = dado
  del file, tipi `A/N/B/L` = `level d8 + bonus` (i dadi sono derivati: cambiarli senza coerenza e' 422 `dikumod.hp_not_dice`; un mob
  nuovo e' `N` se i dadi sono `level d8`, altrimenti `S`), `experience` = esp del file se `>= 0` (formula del gioco), 0 se negativo
  (esperienza fissa: `extra.expRaw`). Campi senza equivalente (`classId`, `debuffSkillId`, `shopId`, `questIds`, `isBanker`, `teaches*`):
  solo il valore neutro. `extra`: `kind` (`S A N B L`), `multiAttack`, `affectedBy` (nomi `dikumodAffectFlags`), `position`, `defaultPos`
  (indici `dikumodPosition`), `sexCode` (grezzo, sola lettura: 3..5 = sesso + 3 con le maschere), `immune`/`mImmune`/`susc` (nomi
  `dikumodImmuneFlags`; impostarle promuove il codice sesso a 3..5, l'unico in cui il gioco le legge), `sound`/`distantSound` (tipo `L`),
  `expRaw`, **`shop`** (negozio di `dikumoddata.shp` con `keeper == vnum`: `{tag, producing[5], profitBuy, profitSell, types[5],
  messages{noSuchItem1.. messageSell}, temper1/2, withWho, room, open1/close1/open2/close2}` o `null`; creato/aggiornato/tolto da qui,
  segue il mob se cambia vnum e va via se il mob e' eliminato), **`script`** (`{name, text}` da `scripts.dat` + `scripts/<Nome>`; `null`
  toglie la riga di `scripts.dat`), `trailing` (dati dopo l'ultimo campo, ignorati dal gioco).
- **Oggetto**: `keywords`, `shortDescription`, `longDescription` (la descrizione a terra), `actionDescription`, `objectType` (tipi senza
  equivalente -> OTHER, il vero e' in `extra.typeRaw`), `weight`, `cost`, `rent` (= `cost_per_day`), `value0..3`, `extraFlags`/`wearFlags`
  (nomi `dikumodExtraFlags`/`dikumodWearFlags`), `affects` dizionario `{nome_apply: somma}`. `extra`: `typeRaw`, **`affects`** = lista ordinata
  `[{location,name,modifier}]` (max 5, lo stesso apply puo' ripetersi: prevale sul dizionario se inviata), `extraDescs`, `forbiddenWear
  {toChar,toRoom}` (blocco `P`), `source`.
- **Reset**: `M` arg1 mob, arg2 max, arg3 stanza (nessun "max in stanza": `arg4` e' ignorato); `O` oggetto/max/stanza/**`arg4` = max in
  stanza** (sempre 5 numeri in scrittura); `G` oggetto/max; `E` oggetto/max + `argStr` slot (`dikumodWearPos`, anche numerico); `P` oggetto/max/
  contenitore; `D` stanza/direzione + `argStr` OPEN/CLOSED/LOCKED; `C` (7) mob/max/bit act; `H` (8) e `F` (9) tipo/valore (tipo 7 = vnum
  di mob); `Z` (10) zona/flag. `max` 0 = nessun limite (come nel gioco). `ifValue` e' l'intero del file, `comment` il commento della riga
  (`; testo`, troncato a 78 caratteri: `fgets(buf, 80)`). Sostituire lo script riusa i comandi invariati (stessi byte) e conserva
  commenti/righe vuote solo se lo script non cambia; se la zona ha `zones/<n>.zon` la scrittura va li'.
- Un patch applica solo i campi **diversi** dal valore corrente: rimandare il DTO letto (`extra` compreso) non cambia nemmeno un byte e
  non riscrive il file. I testi sono mostrati senza il `\n` finale che il gioco richiede (lo riaggiunge la scrittura). Chiavi di `extra`
  sconosciute: 422 `dikumod.extra_unknown`; flag sconosciuti: 422 `dikumod.unknown_flag` (i bit senza nome si chiamano `bitN`).

## Record corrotti e diagnostica

I 33 mob corrotti per variante (dado malformato, record troncato, `~` mancante, numero o lettera tipo corrotti) compaiono in lista e in
`GET /mobs/{vnum}` con nome/descrizione ricavati dal testo e `extra = {corrupted: true, warning: <motivo>, line, raw: <testo del record>}`;
`PUT`/`DELETE` rispondono 409 `dikumod.record_corrupted` e la riscrittura del file li conserva identici. Idem per un negozio troncato
(ignorato dall'API ma conservato) e una zona illeggibile (`zones` con `extra.corrupted`). I `Diagnostic` della libreria (anche gli avvisi:
settore fuori tabella della stanza 13798, comandi di zona con argomenti mancanti, commenti oltre 79 caratteri, vnum doppi) non hanno
ancora un endpoint dedicato.

## Integrita' e vincoli del gioco

Vnum univoci (409 `*.vnum_taken`) e nel range della zona indicata (422 `dikumod.vnum_out_of_range`); cambio vnum/eliminazione bloccati se usati da
comandi di reset (anche `C` e `H`/`F` di tipo 7 per i mob) o, per gli oggetti, come chiave di uscita; il cambio vnum di una stanza aggiorna le
uscite che la raggiungono e i suoi `D`, eliminarla azzera le uscite entranti e toglie i suoi `D`; validazione dei reset con
`rules.validate_script`. Scrittura: `~` nei testi (non c'e' escape), righe di un record `.mob`/`.obj` che iniziano per `#` o `%%` (anche come
frammento da 81 caratteri: `fgets(buf, 82)`) -> 422 `dikumod.unsafe_text`, nessun byte scritto. I record dei file indicizzati restano **in
ordine di vnum** (ricerca binaria del gioco) e il file finisce con `%%`.
Le righe che iniziano per `#` sono invece **ammesse** in nome/descrizione di stanze e zone: `.wld` e `.zon` non sono indicizzati per riga
(`boot_world`/`boot_zones` leggono in sequenza con `fread_string`) e il test di round trip lo verifica. Un carattere non
rappresentabile in `latin-1` (emoji, `€`) -> 422 `dikumod.unencodable_text`, prima di scrivere il primo file.

## Meta e capability

`enums()` = le sette enum standard (con `zoneCommandType` esteso a 0-5 e 7-10) + tabelle `dikumodRoomFlags`, `dikumodExitFlags`, `dikumodActFlags`,
`dikumodAffectFlags`, `dikumodImmuneFlags`, `dikumodExtraFlags`, `dikumodWearFlags`, `dikumodTeleFlags`, `dikumodZoneResetBits`, `dikumodSector`, `dikumodItemType`,
`dikumodPosition`, `dikumodApplyType`, `dikumodWearPos`, `dikumodRace`, `dikumodLiquid`, `dikumodDoorState`, `dikumodMobKind` (flag: `value` = bit; tipi: indice).
`races()` = le 85 razze di `race.h`, `classes()` vuota. Capability: solo `supportsResetScripts` e `supportsExtraDescriptions`.

## Limiti noti

- Il loader C del gioco vede **90 zone** nel file originale (431 comandi `O` a 4 numeri gli fanno fondere tre coppie di zone): l'adapter
  usa le 93 intese e gli indici di posizione, che dopo la prima zona fusa non coincidono con quelli del gioco (rilevante per `Z` e
  `zones/<n>.zon`). Riscrivere una zona porta le sue `O` a 5 numeri; le zone non toccate restano identiche.
- Non gestiti: gilde (`dikumoddata.gui`, `gilde/`), `world/<vnum>` (binari), `mobiles/`, `dikumoddata2/3/4.*` e `.err` dell'editor Windows, mob di tipo
  `D`, linguaggio degli script (solo il testo), `R` (non implementato dal loader). Nessuna transazione tra piu' file; modifiche esterne
  concorrenti non sono rilevate fino alla scrittura successiva.
- `enabled`, `builder`, livelli di zona e `healRate`/`manaRate`/`clanId`/`owner` non esistono in Diku Modificato.

## Cosa informa l'adapter `mapping` generico (YAML, task separato)

Da questo lavoro (non implementato qui): (1) la **grammatica a campi con condizioni** su un valore gia' letto (`sector == -1`, `tele_mask &
2`, `sector in {7,9}`, `flags & 256`, `gold == -1`, `sex in 3..5`, lettera tipo) e liste di sezioni con tag e sentinella e' esattamente cio'
che fanno `parser.py`/`writer.py` (`cscan.CScan` e' il candidato per le primitive dichiarative `string~`, `int`, `flags|`, `dice`); (2) i
**terminatori e i confini dei record per file** (`%%`, `$~`, `S`, `#vnum` a inizio riga) e l'**indicizzazione per offset con ricerca
binaria** (i file devono restare ordinati, `ensure_terminator`); (3) i **ganci in codice** che il YAML non esprime: zona dal vnum per
intervallo di `top` (id = posizione), trasformazioni (`hp = level d8 + bonus`, `exp` negativa, sesso + maschere), join fra file (negozio per
keeper, script, override per-vnum con precedenza in lettura e scrittura), loader tollerante con `Raw` + diagnostica, writer a conservazione
byte, e le regole di integrita' (`rules.validate_script` esteso ai comandi 7-10); (4) le **estensioni dei DTO** gia' fatte qui (`ifValue`,
`comment`, `commandType` intero, `extra` su uscite e reset) e le tabelle per mondo in `enums()` (`dikumod*`/`rom*`), che il mapping generico
dovra' poter dichiarare; (5) il default `read_only: true` per i MUD a file monolitico, da esporre come campo del YAML di mappatura.

## Descrittori delle chiavi di `extra` e dei campi non supportati

`describe()` non dichiara solo i campi del DTO ma anche cio' che il form deve sapere del mondo (il frontend non ha tabelle per tipo di mondo):

- `FieldDescriptor.unsupported`: il mondo non ha il campo (lettura neutra, scrittura solo del valore neutro); implica `readOnly`.
  `readOnly` marca anche i campi derivati (Diku Modificato: `zone.bottomVnum`).
- `ResourceInfo.extraFields[]` (`ExtraFieldDescriptor`): una voce per chiave di `extra` emessa: `name`, `labelKey` (`extra.labels.<name>`,
  traduzione lato frontend, ripiego sul nome), `type` (`text|number|boolean|flags|enum|select|json`; `flags` = lista di nomi, `enum` =
  nome dell'opzione, `select` = valore/indice), `enum` (lista di `GET /api/meta/enums`), `readOnly`, `nullable`, `group`
  (`diagnostic` = `corrupted`/`warning`/`line`/`raw`: mai nel form, il frontend ne ricava il banner e rende il record di sola lettura).
- `ResourceInfo.createAtEnd` (zone): le zone nuove si aggiungono solo in coda, il range di partenza e' calcolato.
- Pachimud: tutto vuoto. BasedMud/Diku Modificato: tabelle in `pachimudeditor_adapter_<kind>/fields.py`. Mapping: ricavate dalla mappatura
  (`EntityMapper.extra_descriptors()`: campi del record non mappati; `unsupported_names()`: campi `const`/senza `from`).
- Gli helper sono in `common/adapters/describe.py` (`xf`, `diagnostic`, `finish_resource`). I test `tests/{dikumod,basedmud,mapping}/test_describe*`
  confrontano le chiavi dichiarate con quelle emesse sui dati reali (`tests/support/describe_check.py`), cosi' non possono divergere.
