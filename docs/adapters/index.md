# Adapter: editare più MUD con lo stesso webeditor

Il backend non parla più direttamente con il database di pachimud: ogni router (zone, stanze, mob,
oggetti, meta) chiama un **`WorldAdapter`**, l'oggetto che sa dove vivono i dati di un "mondo" (un MUD).
Nessun mondo è implicito: i mondi sono quelli di `webeditor_worlds`. Il mondo `kind: pachimud` legge il database del gioco
con SQLAlchemy (schema-on-read, nessun import del pacchetto `pachimud`): vedi "Adapter pachimud".

```
router (apps/*/root.py nel core; nei pacchetti adapter per le pagine specifiche)  ->  AdapterDep  ->  WorldAdapter  ->  DB / file .are / ...
                                         ^
                       registry (common/adapters/registry.py): X-World / ?world=
```

## Struttura

| Percorso (core in `src/pachimudeditor/`, adapter in `adapters/<nome>/src/pachimudeditor_adapter_<nome>/`) | Ruolo |
|---|---|
| `common/adapters/base.py` | interfaccia astratta `WorldAdapter`, `AdapterCapabilities`, `AdapterInfo`, `FieldDescriptor` |
| `common/adapters/models.py` | DTO neutri Pydantic camelCase (Out/In/Patch, page params, `ResetUsage`, `ZoneBundle`, `ImportPreview`) |
| `common/adapters/rules.py` | regole **indipendenti dal backend dati**: validazione script di reset, coerenza uscite, range di zone, vnum liberi, uso nei reset, grafo stanze |
| `common/adapters/layout.py` | layout a bussola del grafo (funzioni pure) |
| `common/adapters/describe.py` | genera i `FieldDescriptor` dai modelli Pydantic |
| `common/adapters/registry.py` | `WorldRegistry`, `register_kind`, `AdapterDep`, `WriteAdapterDep`, `require_capability` |
| `common/adapters/settings.py` | lettura configurazione mondi (`pachimudeditor.yaml` / ambiente) |
| `common/adapters/worlds.py` | `GET /api/worlds` |
| `sdk.py` | **API pubblica per gli adapter esterni** (re-esporta i nomi stabili; vedi "Adapter come pacchetti") |
| `common/adapters/plugins.py` | `AdapterPlugin`, scoperta con `importlib.metadata.entry_points`, caricamento lazy di factory/moduli/regole, stato dei kind (`adapters list`) |
| `adapters/pachimud/` (pacchetto `pachimudeditor-adapter-pachimud`) | `PachimudAdapter` (mixin `zones`, `rooms`, `prototypes`, `meta`) + `params` (database_url/definitions_path/config_path), `schema` (riflessione, revisioni note, controllo), `connection` (engine/sessioni del mondo), `definitions` (razze/classi), `security` (Argon2id), `race_enums`, `transfer/` (schemi, writer/reader, import e anteprima dei YAML di zona), `editor/` (crud, db, reset_usage, istanze), `apps/{world,players,instances,transfer,content}` (le pagine API del gioco), `convert.py` (sapore); vedi [adapter pachimud](pachimud.md) |
| `adapters/basedmud/` (`pachimudeditor-adapter-basedmud`) | `BasedMudAdapter` su file `.are` (libreria `rom_lib` inclusa): `store` (cache/indici/scrittura), `mapping` (ROM <-> DTO), mixin `zones`, `rooms`, `prototypes`, `meta`, `convert.py` (sapore); vedi [adapter basedmud](basedmud.md) |
| `adapters/dikumod/` (`pachimudeditor-adapter-dikumod`) | `DikumodAdapter` sui file dati di Diku Modificato (libreria `dikumod_lib` inclusa): `store` (cache/indici/override), `mapping`, mixin `zones`, `rooms`, `prototypes`, `meta`, `convert.py` (sapore); vedi [adapter dikumod](dikumod.md) |
| `adapters/mapping/` (`pachimudeditor-adapter-mapping`) | `MappingAdapter` generico guidato da un YAML (`schema`, `grammar`, `writer`, `model`, `store`, mixin `zones`/`rooms`/`prototypes`, `adapter`) con `examples/` (`rom.yaml`, `diku_classic.yaml`, `minimud/`); vedi [adapter mapping](mapping.md) |
| `common/adapters/paging.py` | paginazione/ricerca/ordinamento in memoria per gli adapter su file |
| `tests/adapter_contract/` | suite di contratto parametrizzabile sugli adapter |
| `tests/test_adapters.py` | registro, selezione, `/api/worlds`, guardia capability, sola lettura |

## Configurazione e selezione del mondo

In `pachimudeditor.yaml` della cartella di lavoro (oppure `WEBEDITOR_WORLDS` come JSON e `WEBEDITOR_DEFAULT_WORLD` nell'ambiente,
che hanno la precedenza):

```yaml
webeditor_worlds:
  - id: pachimud
    kind: pachimud
    name: Pachimud
    params:
      database_url: sqlite+aiosqlite:////percorso/pachimud/pachimud.db
      definitions_path: /percorso/pachimud/definitions
  - {id: basedmud, kind: basedmud, name: BasedMud, path: /percorso/basedmud/area, read_only: true}
  - {id: tba, kind: mapping, name: tbaMUD, mapping: /percorso/tba.mapping.yaml, path: /percorso/tba/lib}
webeditor_default_world: pachimud     # facoltativo: altrimenti "pachimud" se presente, o il primo
```

Campi di un mondo (`WorldConfig`): `id` (univoco), `kind`, `name`, `path` (cartella/file dei dati per gli
adapter su file), `mapping` (path del YAML di mappatura per `kind: mapping`), `params` (dict libero
dell'adapter), `read_only`, `config_path` (solo `kind: pachimud`, vedi [i parametri del mondo pachimud](pachimud.md#parametri-del-mondo)). Senza configurazione non esiste nessun mondo.

Per richiesta: header `X-World: <id>` oppure query `?world=<id>`; assenti = mondo di default. Id ignoto =
**404 `world.not_found`** (it/en). `GET /api/worlds` elenca i mondi: `id, kind, name, default, capabilities, params (informativi, es. `data_prefix` di dikumod),
resources[{type, fields[{name, type, required, readOnly, enum, nullable}]}]` (i `fields` guideranno i form
generici). Gli errori di configurazione (kind non installato, id duplicati) fanno fallire la costruzione del
registro con `ValueError` (kind non installato: `AdapterUnavailable`, che dice quale extra installare).
