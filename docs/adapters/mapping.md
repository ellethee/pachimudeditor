# MappingAdapter (`kind: mapping`, YAML)

Un solo adapter, un file YAML per MUD: niente codice per i formati a token della famiglia Diku/ROM. Guida con esempio
completo in [guida alla mappatura](mapping-guide.md); codice in `adapters/mapping/src/pachimudeditor_adapter_mapping/`.

```yaml
webeditor_worlds:
  - {id: rom, kind: mapping, name: ROM, mapping: /percorso/rom.yaml, path: /percorso/basedmud/area, read_only: false}
```

`mapping` = YAML di mappatura (obbligatorio), `path` = radice dei dati (obbligatorio), `read_only` come per gli altri adapter.
La mappatura e' validata al caricamento dell'adapter (Pydantic + controlli incrociati: record, campi, tabelle, espressioni, hook,
membri delle enum dei DTO) e gli errori arrivano tutti insieme con `file:riga`. `mapping.schema.json` e' lo schema per
l'autocompletamento (`# yaml-language-server: $schema=...`).

## Architettura

```
mapping.yaml --schema.load_mapping--> MappingSpec
files --store.Store (cache (mtime,size), indici, scrittura atomica)--> Document -> Section -> Record(fields, src, fp)
Record <--model.EntityMapper / ResetMapper--> DTO neutri (+ extra)  --> mixin zones/rooms/prototypes --> WorldAdapter
```

| Modulo | Ruolo |
|---|---|
| `schema.py` | modelli Pydantic del YAML, sintassi compatta dei passi, `load_mapping`, controlli incrociati, `json_schema()` |
| `grammar.py` | `Cursor` (primitivi `fread_*`), `Parser` (campi, `when`, `switch`, `tagged`, sezioni), `Record`/`Section`/`Document` |
| `writer.py` | `write_document`: record invariati byte per byte, nuovi/modificati in forma canonica ricavata dalla stessa grammatica |
| `model.py` | tabelle, `Binding`/`EntityMapper` (campo DTO <-> record, `extra`), `ResetMapper` (comandi del MUD <-> reset neutri) |
| `dsl.py` | espressioni sicure (`ast` con lista bianca, niente `eval`) |
| `hooks.py` | registro degli hook in codice (`field`, `record`, `zone_range`) |
| `store.py` | scoperta file (indice/glob/per tipo), range di zona, indici per vnum, inserimento ordinato, scrittura atomica |
| `base.py`, `zones.py`, `rooms.py`, `prototypes.py`, `adapter.py` | l'adapter: stesse regole di integrita' di BasedMud/Diku Modificato (`common.adapters.rules`, `paging`) |

## Convenzioni

- `id == vnum` per stanze, mob e oggetti; zona: `model.zone.id` = `bottom`, `top` o `position` (senza valore valido/univoco:
  `-(posizione)`); uscita `vnum * exit_id_stride + direzione`; extra description `vnum * extra_id_stride + posizione`;
  reset = posizione nello script (commenti e comandi ignoti esclusi).
- Un patch applica solo i campi diversi dal valore corrente (rimandare un DTO letto non cambia byte); i campi del DTO senza
  equivalente valgono il valore neutro e accettano solo quello (422 `mapping.field_unsupported`, o ignorati con `soft`).
- `extra` (camelCase) = tutti i campi del record non consumati dal DTO, riscrivibili; zone: anche `file` e `style`.
- Errori: gli stessi codici del contratto (`rooms.vnum_taken`, `zones.not_empty`, ...) piu' `mapping.*` (messaggi it/en in
  `pachimudeditor_adapter_mapping/locale/`): `unknown_flag`, `unknown_name`, `extra_unknown/invalid/readonly`, `field_unsupported/readonly`,
  `unsupported_value`, `vnum_out_of_range`, `invalid_file_name`, `file_exists`, `zone_*`, `clone_unsupported`,
  `reset_unmapped_commands`, `reset_type_unsupported`.
- Capability: `supports_reset_scripts` se la zona ha `resets`, `supports_extra_descriptions` se la stanza ha
  `extra_descriptions`; le altre `False`.

## Come scrivere la mappatura di un nuovo MUD (passi)

1. **Guarda i file**: per ogni tipo di record, marcatore iniziale, terminatore, tipi dei campi, righe opzionali.
2. **`layout`**: un file per zona (`zone_files`, con `index` e/o `glob`) oppure un file per tipo (`type_files` + `zone_range`).
3. **`grammar.files`**: sezioni in ordine canonico con `header`, `record`, `entity`, `until`, `tail`; `end` per `#$`.
4. **`grammar.records`**: i passi (`nome: tipo`, `line:`, `when:`, `switch:`, `tagged:`); `key` = campo vnum.
5. **`tables`**: nomi dei flag/enum (inline o da file) con `expose` per `enums()`.
6. **`model`**: per ogni entita' i `fields` (`from`, `expr`+`to`, `map`, `null_if`, `const`, `pairs`, `hook`), `defaults`,
   `exits`/`extra_descriptions`, `exit`, `reset.commands`.
7. **`hooks`/`rules`/`meta`** solo se servono.
8. **Prova** (`load_mapping` da' gli errori con riga), poi aggiungi il mondo a `webeditor_worlds` e una factory a
   `ADAPTER_FACTORIES` in `tests/adapter_contract/conftest.py`: la suite di contratto deve passare per intero.

## Riferimento rapido

- **Primitive**: `number float word string_tilde line_text flags dice tag enum`; opzioni `count optional same_line default
  width quote lead write as raw tolerant table`.
- **Blocchi**: `line`, `literal`, `when/then/else`, `switch/cases/default`, `tagged` (`end`, `end_before`, `tag_field`,
  `ignore_case`, tag `"?"`, `into`, `write_if`, `inline`, `glue`); record con `parser:` (hook) e `blank_after`.
- **`FieldMap`**: `from expr to map unmapped null_if const soft hook pairs in_extra`.
- **DSL**: costanti, nomi dei campi (+ `value`), `+ - * / // %`, `& | ^ << >> ~`, `and or not`, confronti, `a if c else b`,
  indici, liste; funzioni `int str float bool len min max abs strip lower upper split join replace startswith get
  int_or_none re_group re_sub has_flag set_flag`. Un campo mancante vale `None`.
- **Hook** (registrati in codice, dichiarati in `hooks:`): `field` (`read(fields)`, `write(fields, valore)`), `record`
  (`parse(cursor)`, `write(fields)`), `zone_range` (`(zone) -> [(bottom, top)]`); inclusi `zone_from_top` e
  `rom_credits_min_level/max_level/builder`.

## Prove (test)

`uv run pytest tests/mapping tests/mapping_http tests/adapter_contract`:

- `tests/mapping/test_rom_equivalence.py`: `rom.yaml` legge **tutti** i `.are` reali di basedmud (copie temporanee) con gli stessi
  conteggi e campi chiave di `pachimudeditor_adapter_basedmud.rom_lib`, li riscrive byte per byte, un mob modificato riscrive solo il suo blocco, e
  `MappingAdapter` e `BasedMudAdapter` danno gli stessi DTO e (a parita' di operazioni) gli stessi file;
- `tests/mapping/test_diku_classic.py`: `diku_classic.yaml` su un mondo sintetico di record reali di Diku Modificato, piu' i file Diku Modificato interi
  (`.zon`/`.wld`/`.obj` si leggono e si riscrivono identici; `.mob`/`.shp` no, vedi limiti);
- `tests/mapping/test_guide_example.py`: l'esempio MiniMUD della guida; `test_engine.py`, `test_dsl.py`, `test_schema.py`,
  `test_adapter_meta.py`: primitive, DSL sicuro, errori con riga, JSON Schema in sincrono;
- `tests/adapter_contract`: varianti `mapping` (mondo vuoto) e `mapping_rom_copy` (copia delle aree reali);
- `tests/mapping_http/test_http.py`: route reali con `X-World` (richiede il registro del kind: vedi `src/pachimudeditor/modules.py`).

## Limiti rispetto agli adapter scritti a mano (BasedMud, Diku Modificato)

- Grammatica rigorosa: nessun recupero dei record corrotti (nessun `Raw`, nessuna diagnostica a posteriori): un record
  malformato e' un errore con riga/colonna. I file Diku Modificato `.mob`/`.shp` interi non si leggono; `DikumodAdapter` si'.
- Nessun join fra file o sezioni: negozi/spec_fun ROM legati al mob, override per-vnum di Diku Modificato (`rooms/<vnum>`...), script e
  gilde non sono esposti (le sezioni ROM sono parsate e conservate).
- Comandi di reset senza tipo neutro (Diku Modificato `C H F Z`) non elencati; sostituire lo script li cancellerebbe, quindi e' rifiutato.
- Valori che dipendono dal tipo (v0-v4 degli oggetti, hit point `S` vs `A/N/B/L`) solo con `expr`; i `valueN` a lettere/nomi
  sono `null`; classi, quest, esperienza non esistono (valore neutro).
- `type_files`: zone nuove solo in coda, niente clonazione ne' `enabled`, `bottomVnum` derivato.
- Formati non a token (delimitatori, XML, JSON) solo con un hook di record.
- Un solo scrittore per volta, nessuna transazione fra piu' file, modifiche esterne concorrenti non rilevate fino alla
  scrittura successiva.
