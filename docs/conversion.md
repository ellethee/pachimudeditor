# Conversione tra mondi

Copia **zone** (con stanze, uscite, extra description, mob, oggetti e script di reset) da un mondo del webeditor a un altro:
BasedMud (`.are` ROM) -> pachimud (DB), Diku Modificato (Diku) -> pachimud, pachimud -> BasedMud, Diku Modificato <-> BasedMud, e qualunque mondo
`mapping` con il convertitore generico. Il codice e la mappa dei moduli sono in [la pagina SDK degli adapter](adapters/sdk.md), sezione "Conversione tra mondi".

## Uso

Pagina **Conversione** (voce di menu, visibile solo con almeno due mondi configurati):

1. scegli mondo sorgente, mondo di arrivo (quelli in sola lettura sono disabilitati) e le zone (con ricerca);
2. scegli la politica dei vnum (`Mantieni`, `Somma uno scostamento`, `Primo intervallo libero`) e cosa fare se la zona
   esiste gia' (`Salta` oppure `Sostituisci`); puoi escludere reset, uscite ed extra description;
3. **Anteprima** (nessuna scrittura): tabella delle zone con azione e range, totali per tipo, conflitti, perdite
   raggruppate per gravita'/tipo (blu = informazione, arancio = approssimato, rosso = perso) e tabella dei vnum;
4. spunta la conferma e **Converti**; a fine corsa il rapporto dice cosa e' stato scritto, o che tutto e' stato annullato.
   "Apri le zone nel mondo di arrivo" passa al mondo di arrivo e apre l'elenco zone.

API (autenticata, i mondi sono nel corpo, **non** in `X-World`):

```
GET  /api/convert/pairs     mondi e coppie (convertitore specific|generic, allowed, reason)
POST /api/convert/preview   corpo sotto; sempre dry-run
POST /api/convert/run       scrive solo con dryRun=false E confirm=true (altrimenti dry-run / 422 convert.confirm_required)
{ "sourceWorld": "basedmud", "targetWorld": "pachimud", "zoneIds": [3700],
  "vnumPolicy": {"mode": "keep" | "offset" | "shift_to", "offset": 0},
  "onConflict": "skip" | "replace", "convertResets": true, "convertExits": true, "convertExtraDescriptions": true,
  "dryRun": true, "confirm": false }
```

`zoneIds` sono gli id delle zone **del mondo sorgente** (`GET /api/zones` con `X-World` del sorgente). Errori: 409
`world.read_only` (arrivo in sola lettura), 422 `convert.same_world`, 404 `world.not_found` / `convert.zone_not_found`,
422 `convert.offset_negative`. Giornale: se `WEBEDITOR_CONVERT_JOURNAL_DIR` (o `webeditor_convert_journal_dir` in
`pachifast.yaml`) e' impostata, ogni esecuzione vera scrive `convert-<data>-<id>.json` con piano e rapporto.

## Come funziona

1. **Lettura** delle zone sorgente e di un indice (vnum/zona) del mondo di arrivo.
2. **Pianificazione.** Per ogni zona: vnum di zona, range e scostamento secondo la politica. Il range effettivo e' quello
   dichiarato allargato al contenuto (una zona `0 0` prende min-max del contenuto). `keep` non cambia nulla; `offset N`
   somma `N` a vnum di zona, range e contenuto; `shift_to` assegna il primo intervallo libero (`next_zone_vnum`), le zone una
   dopo l'altra. Una zona dell'arrivo "corrisponde" se ha lo stesso vnum di zona, oppure stesso range e stesso nome.
3. **Conflitti.** Corrispondenza trovata: `skip` (default) o `replace`. Range che tocca un'altra zona o vnum di contenuto gia'
   usato da un'altra zona: la zona e' **bloccata** (non scritta, le altre proseguono).
4. **Conversione** per entita' con il convertitore della coppia; un elemento non valido nel mondo di arrivo e' scartato
   (`entity_invalid`). Poi i **riferimenti**: destinazione e chiave delle uscite e argomenti dei reset (per semantica del
   comando) passano dalla tabella di rimappatura; fuori dalla conversione restano solo se l'entita' esiste nell'arrivo,
   altrimenti l'uscita/il comando e' scartato. Un comando che dipende da uno scartato cade a sua volta (`G/E/H/F/Z` dopo un
   mob scartato, `ifFlag` dopo un comando scartato). Per i mondi che tengono lo stato porta nei reset `D` (BasedMud, Diku Modificato) si
   aggiunge un `D` per ogni porta chiusa/serrata non coperta.
5. **Scrittura**: zona, stanze (+extra description), oggetti, mob per tutte le zone; poi le uscite (seconda passata); poi i
   reset. `replace` fa prima un'istantanea della zona di arrivo e la svuota (reset, stanze, mob, oggetti).
6. **Rollback** best effort a un errore: si cancella cio' che questa esecuzione ha creato e le zone `replace` tornano
   all'istantanea. Limite: le uscite *di altre zone* verso stanze cancellate da `replace` vengono azzerate dall'adapter e
   **non** si ripristinano.

## Architettura dei convertitori

Un *sapore* per mondo (`pachimud`, `basedmud`, `dikumod`) traduce da/verso il **pivot** (semantica pachimud/ROM); ogni coppia e'
`target.from_pivot(source.to_pivot(x))`. Conseguenza: cio' che il pivot non esprime (negozi, spec_fun, affect dei mob, ...)
si perde anche tra due mondi che lo avrebbero entrambi (es. BasedMud -> Diku Modificato): e' sempre riportato come perdita `dropped`.
Le coppie senza sapore (mondi `mapping`, ...) usano il convertitore generico: campi del nucleo copiati, `extra` scartato.
Vocabolario del pivot: nomi di flag ROM minuscoli, AC in scala piccola (`-10..10`), slot di vestizione col nome del flag
(`wield`), razze = id di `definitions/races`.

## Mappature (le stesse tabelle sono in `common/adapters/convert/tables.py` e in `convert_tables.py` di ogni adapter)

### BasedMud (ROM) -> pachimud

| Dato | Regola | Perdita |
|---|---|---|
| zona | nucleo; `lifespan`/`resetMode` sono costanti ROM | `extra` (file, credits, security) info |
| stanza | flag filtrati sui nomi ROM; settore dell'adapter (ROM 8/10 approssimati) | flag sconosciuti (warning) |
| uscita | porta/stato/chiave invariati; destinazione rimappata | uscite verso stanze fuori conversione: `dropped` |
| mob | `armorClass / 10` (ROM x10); `thac0`, dadi, `gold`, `sex`, `alignment` invariati; `npc` e `unused_*` impliciti; razza `song bird` -> `song_bird` se esiste in `definitions/races`, altrimenti `raceId` vuoto (warning) | negozio, `spec_fun`, mobprog, affect/off/imm/res/vuln: `dropped`; form, parti, taglia, materiale, posizioni, gruppo, tipo di danno, `mana`, `ac[1..3]`: info |
| oggetto | tipo/flag/apply per nome ROM; valori per tipo: arma `[dadi, facce, 0, colpo]` (colpo ROM -> scostamento di pachimud, `pierce` = 11); armatura `v0`; contenitore/liquido: valori persi; pozioni/rotoli/bacchette: incantesimi persi | `flagAffects`, extra description dell'oggetto, `level`/`material`/`condition`, tipi ROM senza equivalente -> `OTHER` |
| reset | stessi argomenti; `O`: `max` 0 -> 99 nel mondo e 1 per stanza; `E` slot `wielded` -> `wield`, `lfinger`/`rfinger` -> `finger`, ...; `P` quantita' > 1 persa; `R` (ROM) = randomizza uscite, come pachimud | slot sconosciuto: comando scartato |

### pachimud -> BasedMud (inverso, per quanto possibile)

`armorClass * 10` su tutti i quattro AC; flag in minuscolo filtrati sulle tabelle ROM; `experience`, `classId`, `debuffSkillId`,
`shopId`, `questIds`, `isBanker`, `teaches*` non esistono in ROM (azzerati, riportati); oggetti: `rent`/`actionDescription`
persi, valori riscritti nei token ROM (arma `exotic dadi facce <colpo> 0`, armatura `v0 v0 v0 v0`, contenitore e liquidi con
default); reset `O` con `max` 0 (ROM lo ignora); slot di `E` `wield` -> `wielded`, `finger` -> `lfinger`, `neck` -> `neck1`, `wrist` -> `lwrist`.

### Diku Modificato -> pachimud

| Dato | Regola | Perdita |
|---|---|---|
| zona | `builder` vuoto, livelli 1; durata e modo di reset (`NEVER/EMPTY/ALWAYS`) invariati | `extra` info |
| stanza | flag via tabella (`peaceful` -> `safe`, ...); settore dell'adapter (8 aria -> `FLYING`, 10-12 approssimati) | flag senza equivalente (es. `no_summon`, `tunnel`), teletrasporto/fiume/luce/`moblim` |
| uscita | `ISDOOR` -> porta, `PICKPROOF`; stato dal `D` o dai bit | bit `secret`, `climb`, `notbash`, ... e comando di apertura |
| mob | AC e `thac0` invariati (stessa scala di pachimud); `act` via tabella (`stay_zone` -> `stay_area`, `magic_user` -> `mage`); `isnpc` implicito; razza via alias (`elven` -> `elf`, `dragon_red` -> `dragon`) | negozio `.shp`, script, `affectedBy`, immunita', suoni, posizioni, attacchi multipli; mob corrotti non convertiti |
| oggetto | arma Diku `[v1, v2, 0, v3]`; flag e apply via tabella (`str` -> `strength`, `ac` -> `armor class`, `waiste` -> `waist`) | flag/apply senza equivalente (`anti_mage`, `chr`, `throw`...), extra description, `forbiddenWear`, incantesimi, capacita'/chiave contenitori |
| reset | `max` 0 = "nessun limite": `M`/`O` -> 99, `G/E/P` -> vuoto; `O` `arg4` = massimo per stanza; slot di `E` (`finger_l` -> `finger`, `waiste` -> `waist`, `eyes` -> `eye`); `ifValue` > 0 -> `ifFlag` | `C H F Z` (charm, odio, paura, zona) scartati con i comandi che ne dipendono; commenti |

### pachimud -> Diku Modificato, Diku Modificato <-> BasedMud

Via pivot (tabelle inverse): `isnpc` sempre aggiunto ai mob, sesso `BOTH` -> neutro, razze via alias inverso o vuote, zona senza
builder/livelli/`enabled`, stanza senza `healRate`/`manaRate`/`clanId`/`owner`, apply max 5, reset `R` scartato e `M` senza
`arg4` (Diku Modificato non ha il massimo per stanza). La zona va in **coda** al mondo Diku Modificato (usare `shift_to` o un range che inizi dopo l'ultima).
Diku Modificato <-> BasedMud passa dal pivot: AC x10/ / 10, flag tradotti due volte; negozi e script di Diku Modificato / negozi e `spec_fun` di ROM si perdono.

### Mondi `mapping` (ripiego generico)

Nucleo copiato (`flags` e `sectorType` come sono, quindi sensato solo tra vocabolari compatibili) e `extra` scartato con una
perdita `extra_dropped`. Per regole proprie scrivere un sapore o un `PairConverter` registrato (vedi [la pagina SDK degli adapter](adapters/sdk.md)).

## Perdite note e limiti

- Il pivot e' pachimud: dati che pachimud non ha non attraversano mai il motore tra mondi ricchi (BasedMud <-> Diku Modificato).
- Le uscite verso stanze di zone non convertite (e non presenti nell'arrivo) sono scartate: convertire insieme le zone collegate.
- `replace` cancella: le uscite di altre zone verso le stanze sostituite sono azzerate dall'adapter (non ripristinabili dal rollback).
- Il rollback e' best effort (nessuna transazione tra piu' file/righe); gli errori di rollback sono nel rapporto (`rollbackErrors`).
- Le conversioni leggono tutto il mondo di arrivo (indice vnum): con Diku Modificato (migliaia di stanze) l'anteprima richiede qualche secondo.
- Valori di arma/armatura/AC convertiti per convenzione (scala AC, scostamento del colpo): vanno riviste a mano per il bilanciamento.

## Riferimento tecnico

Il motore `common/adapters/convert/` copia zone (stanze, uscite, extra description, mob, oggetti, script di reset) da un
mondo a un altro **solo tramite `WorldAdapter`**; guida d'uso, tabelle di mappatura e perdite note in
questa pagina. Mappa del codice:

| Percorso (in `src/pachimudeditor/`) | Ruolo |
|---|---|
| `common/adapters/convert/models.py` | piano (`ConvertPlan`, `VnumPolicy`), `LossItem`, `ConvertReport` |
| `common/adapters/convert/converter.py` | `PairConverter` (puro: DTO `Out` -> DTO `In` + perdite), registro `register_converter` / `get_converter`, ripiego `GenericConverter` |
| `common/adapters/convert/{reader,planner,build,writer,engine}.py` | lettura, politica di vnum e conflitti, conversione e riferimenti, scrittura con rollback, orchestrazione `convert(source, target, plan)` |
| `common/adapters/convert/journal.py` | giornale JSON (`WEBEDITOR_CONVERT_JOURNAL_DIR` o `webeditor_convert_journal_dir`; non impostato = nessun giornale) |
| `common/adapters/convert/{flavor,helpers,tables}.py` | `Flavor`/`ComposedConverter` e gli helper/tabelle del **pivot** (semantica pachimud/ROM) condivisi dai sapori |
| `pachimudeditor_adapter_<kind>/convert.py` | il `Flavor` del kind (pachimud, basedmud, dikumod), dichiarato in `AdapterPlugin.flavor`; le tabelle specifiche stanno accanto (`convert_tables.py`) |
| `apps/convert/` | API `/api/convert` (`GET /pairs`, `POST /preview`, `POST /run`); i mondi sono nel corpo, non in `X-World` |

**Dove stanno le regole.** Le regole di conversione non sono per coppia ma per *mondo*: il motore e' a pivot (`A -> pivot -> B`), quindi
le regole di un mondo valgono verso qualunque altro e **vivono nell'adapter di quel mondo** (`convert.py`, dichiarato con
`AdapterPlugin.flavor`). Nel core restano solo `Flavor`, `ComposedConverter`, gli helper e le tabelle del pivot. `get_converter(a, b)`
compone i sapori dei due plugin installati; se uno dei due manca (o e' `mapping`) vale il ripiego generico.

**Come aggiungere un convertitore.** (1) Nuovo mondo con regole proprie: scrivere un `Flavor` nel pacchetto del suo adapter
(`*_to_pivot` e `*_from_pivot` per zona, stanza, uscita, mob, oggetto, reset; i default sono l'identita') con le sue tabelle, e
indicarlo in `AdapterPlugin.flavor`: le coppie con gli altri sapori installati sono composte automaticamente. (2) Una coppia con
regole che il pivot non puo' esprimere (es. due mondi che condividono i negozi): sottoclasse di `PairConverter` registrata con
`register_converter` all'import del plugin (ha la precedenza sulla coppia composta). (3) Senza nulla di tutto cio' vale il ripiego
generico (nucleo copiato, `extra` scartato e riportato).
Ogni metodo restituisce `Converted(valore | None, [LossItem])`: `None` scarta l'elemento. Le perdite hanno `code` (voce
`convert.loss.<code>` dei cataloghi it/en di `apps/convert/locale`), `params`, `field`, `severity` (`info` | `warning` | `dropped`).
I vnum restano quelli sorgente nel convertitore: li riscrive il motore.

**Politica di vnum** (`plan.vnumPolicy`): `keep`; `offset` (somma a vnum di zona, range, contenuto); `shift_to` (primo
intervallo libero dell'arrivo con `next_zone_vnum`, le zone una dopo l'altra). Riferimenti fuori dalla conversione (uscite,
chiavi, reset) restano validi solo se l'entita' esiste gia' nell'arrivo, altrimenti uscita/comando sono scartati con una perdita.

**Sicurezza.** `dryRun` di default; la scrittura vera richiede `dryRun=false` e `confirm=true`; arrivo `read_only` (409
`world.read_only`) o stessi dati della sorgente (422 `convert.same_world`) rifiutati; un errore a meta' annulla quanto creato
(le zone `replace` tornano all'istantanea; le uscite entranti azzerate dalla cancellazione non sono ripristinabili).
