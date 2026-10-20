# Adapter come pacchetti (plugin)

Ogni `kind` e' un **pacchetto Python separato** (`pachimudeditor-adapter-<kind>`, modulo `pachimudeditor_adapter_<kind>`) nello
stesso monorepo (`adapters/<kind>/`, membri dell'uv workspace). Il core non li importa mai (lo verifica
`tests/core/test_boundaries.py`): li **scopre** con gli entry point del gruppo `pachimudeditor.adapters` ed e' esposto come
*extras*: `pip install 'pachimudeditor[dikumod]'` (o `pachimud`, `basedmud`, `mapping`, `all`).

| Kind | Pacchetto / extra | Cosa porta |
|---|---|---|
| `pachimud` | `pachimudeditor-adapter-pachimud` | database di gioco SQLAlchemy + pagine world/players/instances/transfer/content |
| `basedmud` | `pachimudeditor-adapter-basedmud` | file `.are` (ROM 2.4 / QuickMUD / basedmud) con la libreria `rom_lib` |
| `dikumod` | `pachimudeditor-adapter-dikumod` | Diku Modificato (`dikumoddata.*`) con la libreria `dikumod_lib` |
| `mapping` | `pachimudeditor-adapter-mapping` | MUD su file descritto da un YAML di mappatura (esempi `rom.yaml`, `diku_classic.yaml`) |

`pachimudeditor adapters list` mostra i plugin scoperti (kind, stato, pacchetto, versione) e, per quelli ufficiali non
installati, il comando per aggiungerli; `info`, `worlds list|check` e `init` riportano lo stesso (il `pachimudeditor.yaml`
generato contiene l'esempio commentato di ogni adapter installato e un suggerimento per gli altri).

## Come funziona la scoperta

1. All'avvio il core legge gli entry point del gruppo `pachimudeditor.adapters` (`common/adapters/plugins.py::discover`) e
   importa **solo** il modulo `plugin` di ciascuno: un `AdapterPlugin` fatto di sole stringhe `"modulo:attributo"`.
2. Un kind **non configurato** non importa nulla di piu' (ne' factory, ne' moduli API, ne' regole di conversione).
3. Per ogni `kind` con almeno un mondo configurato: `build_modules(kinds)` aggiunge i `modules` del plugin (route e cataloghi it/en);
   il registro dei mondi crea l'adapter con la `factory` al primo uso; `validate(config)` gira all'avvio (parametri sensati);
   `get_converter(a, b)` compone i `flavor` dei due plugin (vedi "Conversione tra mondi").
4. Un plugin che non si importa **non fa cadere il core**: avviso nel log, il kind risulta `ERRORE` in `adapters list` e un
   mondo di quel kind e' un errore leggibile all'avvio. Un mondo con un kind non installato da' un errore che indica cosa
   installare (`kind 'dikumod' non disponibile: installare l'adapter: pip install 'pachimudeditor[dikumod]'`).
5. `register_kind(kind, factory)` resta per l'uso programmatico/test e ha la precedenza sui plugin.

## Scrivere un adapter esterno

Struttura (esempio `pachimudeditor-adapter-miomud`):

```
adapters/miomud/                       # o un repository a parte
  pyproject.toml
  src/pachimudeditor_adapter_miomud/
    __init__.py                        # leggero: nessun import pesante
    plugin.py                          # l'AdapterPlugin (solo stringhe)
    adapter.py                         # class MioMudAdapter(WorldAdapter)
    module.py                          # AppModule con i cataloghi it/en (e le route, se servono)
    locale/{__init__,it,en}.py         # MESSAGES = {"miomud.xxx": "..."}
```

`pyproject.toml`:

```toml
[project]
name = "pachimudeditor-adapter-miomud"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = ["pachimudeditor>=0.1.0,<0.2"]      # + le tue (il core non porta sqlalchemy & co. oltre a quanto serve a pachifast)

[project.entry-points."pachimudeditor.adapters"]
miomud = "pachimudeditor_adapter_miomud.plugin:plugin"   # il nome dell'entry point DEVE essere il kind

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pachimudeditor_adapter_miomud"]
```

`plugin.py`:

```python
from pachimudeditor.sdk import AdapterPlugin

plugin = AdapterPlugin(
    kind="miomud",
    sdk_version="1.2",  # il valore di `pachimudeditor.sdk.SDK_VERSION` con cui scrivi e provi l'adapter (letterale, non importato)
    description="il mio MUD (file dati)",
    factory="pachimudeditor_adapter_miomud.adapter:MioMudAdapter",  # (WorldConfig) -> WorldAdapter
    modules=("pachimudeditor_adapter_miomud.module:module",),  # solo se esiste un mondo miomud
    flavor="pachimudeditor_adapter_miomud.convert:MioMudFlavor",  # facoltativo: conversione da/verso gli altri mondi
    validate="pachimudeditor_adapter_miomud.adapter:validate_world",  # facoltativo: alza ValueError se i parametri non vanno
    example="# - { id: miomud, kind: miomud, path: /percorso/dati }\n",  # per il pachimudeditor.yaml di `init`
)
```

`adapter.py` minimo (scheletro provato: viene scoperto da `adapters list` e `worlds check` risponde `ok`; `check` chiama `list_zones`, gli altri
metodi astratti di `WorldAdapter` vanno implementati prima di usare il mondo davvero):

```python
from typing import Any

from pachimudeditor.common.adapters.models import ZoneOut, ZonePageParams
from pachimudeditor.sdk import AdapterCapabilities, AdapterInfo, WorldAdapter, WorldConfig, make_page


def _todo(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError


_Base = type("_Base", (WorldAdapter,), {n: _todo for n in WorldAdapter.__abstractmethods__})  # segnaposto: sostituire con i metodi veri


class MioMudAdapter(_Base):
    def __init__(self, config: WorldConfig) -> None:
        self.config = config

    async def list_zones(self, params: ZonePageParams):
        return make_page(ZoneOut, [], 0, params)

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(read_only=True)

    def describe(self) -> AdapterInfo:
        return AdapterInfo(id=self.config.id, kind=self.config.kind, name=self.config.name or "", capabilities=self.capabilities(), resources=[])


def validate_world(config: WorldConfig) -> None:
    if not config.path:
        raise ValueError("manca path")
```

`module.py` (`AppModule` si importa da `pachifast`, non dall'SDK):

```python
from pachifast import AppModule

module = AppModule(name="pachimudeditor_adapter_miomud", kind="common", locale_package="pachimudeditor_adapter_miomud.locale")
```

(per route proprie aggiungere `router_modules=(...)`, vedi `adapters/pachimud/.../apps/`).

Per usare l'adapter nel monorepo basta aggiungerlo a `adapters/` (workspace member), a `[tool.uv.sources]` e al gruppo `dev` del
`pyproject.toml` del core, e come extra (`miomud = ["pachimudeditor-adapter-miomud>=0.1.0"]`); fuori dal monorepo basta
`pip install pachimudeditor pachimudeditor-adapter-miomud`. La checklist qui sotto vale come per ogni adapter.

## Helper SDK disponibili

Riepilogo di `pachimudeditor.sdk.__all__`, per famiglia:

| Famiglia | Simboli |
|---|---|
| Scoperta | `AdapterPlugin`, `AdapterUnavailable`, `ENTRY_POINT_GROUP`, `SDK_VERSION` |
| Contratto | `WorldAdapter`, `AdapterCapabilities`, `AdapterInfo`, `ResourceInfo`, `ResourceType`, `FieldDescriptor`, `ExtraFieldDescriptor` |
| Registro/dipendenze | `WorldConfig`, `register_kind`, `get_registry`, `AdapterDep`, `WriteAdapterDep`, `require_capability` |
| Descrizione campi | `describe_resource`, `finish_resource`, `xf`, `diagnostic` |
| Liste | `make_page`, `paginate_list` |
| Errori/DTO | `conflict`, `not_found`, `PatchModel` |
| Regole | `rules` (reset, uscite, range, grafo, uso) |
| Conversione | `Flavor`, `ComposedConverter`, `PairConverter`, `ConvertContext`, `Converted`, `loss`, `to_in`, `extra_dropped`, `convert_helpers`, `convert_tables` |
| File (SDK 1.2) | `atomic_write_bytes(path, data)`: scrittura atomica (temporaneo nella stessa cartella, `fsync`, `os.replace`); segue i symlink, preserva permessi e proprietario, pulisce il temporaneo in caso di errore |

Per scrivere un file dell'adapter usa `atomic_write_bytes` invece di `open(..., "w")`: un crash a meta' non lascia file troncati.

## API pubblica del core (`pachimudeditor.sdk`)

Gli adapter importano dal core **solo** questi moduli (verificato da `tests/core/test_boundaries.py`); il resto e' interno:

- `pachimudeditor.sdk`: `AdapterPlugin`, `AdapterUnavailable`, `ENTRY_POINT_GROUP`, `SDK_VERSION`, `atomic_write_bytes`;
  `WorldAdapter`, `AdapterCapabilities`, `AdapterInfo`, `ResourceInfo`, `ResourceType`, `FieldDescriptor`, `ExtraFieldDescriptor`;
  `WorldConfig`, `register_kind`, `get_registry`, `AdapterDep`, `WriteAdapterDep`, `require_capability`;
  `describe_resource`, `finish_resource`, `xf`, `diagnostic` (descrittori dei campi); `make_page`, `paginate_list` (paginazione in memoria);
  `rules` (modulo: validazione reset, uscite, range, grafo, uso nei reset); `conflict`, `not_found` (errori HTTP con codice), `PatchModel`;
  conversione: `Flavor`, `ComposedConverter`, `PairConverter`, `ConvertContext`, `Converted`, `loss`, `to_in`, `extra_dropped`,
  `convert_helpers` e `convert_tables` (moduli: flag, razze, valori per tipo, argomenti dei reset; tabelle pivot).
- `pachimudeditor.common.adapters.models`: i DTO neutri (`ZoneOut/In/Patch`, `RoomOut/In`, `MobOut/In`, ... , `ResetCommandOut/In`, page params, `Option`, `ContentRef`).
- `pachimudeditor.common.enums`: le enum dei DTO (`Direction`, `DoorFlag`, `SectorType`, `Sex`, `ObjectType`, `Position`, `ZoneCommandType`, `ZoneResetMode`).
- `pachimudeditor.common.adapters.convert.helpers`: stesse funzioni di `sdk.convert_helpers`, importabili per nome.

Compatibilita': `pachimudeditor.sdk.SDK_VERSION` (la costante e' la fonte di verita': `python -c "from pachimudeditor.sdk import SDK_VERSION; print(SDK_VERSION)"`)
sale di **minor** per le aggiunte e di **major** per le rotture. Gli adapter dichiarano `pachimudeditor>=X,<Y` e, nel loro `AdapterPlugin`,
`sdk_version="<major>.<minor>"` con l'SDK con cui sono stati scritti (un adapter che usa un helper aggiunto in 1.2 dichiara almeno "1.2"
e un `pachimudeditor` che lo offre). Regola applicata dal core alla scoperta: **major diversa** (piu' nuova o piu' vecchia) = il plugin e'
rifiutato, il `kind` risulta in errore (`broken` in `adapters list`, 'SDK incompatibile ...' nel messaggio dei mondi) e il resto del core
funziona; **minor diversa** = compatibile. Le aggiunte di minor sono additive (gli adapter scritti per un minor precedente restano validi);
la storia delle versioni e' nel [CHANGELOG](../changelog.md).
Senza `sdk_version` (adapter datati) non c'e' controllo. Provato da `tests/core/test_plugins.py`. I test del core NON richiedono nessun adapter: `tests/core/` usa adapter fittizi registrati con entry point
sintetici (`tests/core/fake_adapter`), un buon modello per testare la scoperta nel tuo adapter.

# Interfaccia `WorldAdapter` (async, tranne `capabilities`/`describe`)

- Identita': `capabilities()`, `describe()`.
- Zone: `list_zones, get_zone, create_zone, update_zone, delete_zone, zone_summary, next_zone_vnum,
  next_content_vnum, clone_zone, list_reset_commands, replace_reset_commands, validate_reset_commands`.
- Stanze: `list_rooms, get_room, create_room, update_room, delete_room, clone_room, room_graph, room_usage,
  create_exit, update_exit, delete_exit, create_extra_description, update_extra_description,
  delete_extra_description`.
- Mob: `list_mobs, get_mob, create_mob, update_mob, delete_mob, mob_usage`.
- Oggetti: `list_objects, get_object, create_object, update_object, delete_object, object_usage`.
- Meta: `enums, races, classes`.
- Opzionali (default 409 `world.capability_missing`): `export_zone_bundle`, `import_zone_dir`
  (capability `supports_transfer`); `aclose()` per rilasciare risorse.

## Convenzioni

- **Nessun tipo SQLAlchemy** nell'interfaccia: si scambiano solo i DTO di `common.adapters.models`.
- **`id`**: lo sceglie l'adapter ed e' opaco per il client. pachimud: chiave primaria della riga. **Adapter
  su file: `id == vnum`** (il vnum e' l'identita' stabile nel mondo; l'API mantiene il campo `id`). Le
  uscite e le extra description non hanno vnum: per un adapter su file l'`id` puo' essere un indice
  stabile (es. direzione per le uscite, posizione per le extra) purche' coerente tra le letture.
- **`extra: dict`** su zona/stanza/mob/oggetto (e, in uscita, su uscite e comandi di reset) (Out, In, Patch): campi specifici del MUD fuori dal modello
  neutro. pachimud lo lascia `{}` in uscita e rifiuta valori in ingresso (422 `world.extra_unsupported`).
- **Errori**: `HTTPException` con codice stabile, stesso catalogo i18n per ogni adapter
  (`common.editor.errors.not_found/conflict`, `pachifast.i18n.api_error`). Un adapter che aggiunge codici
  nuovi aggiunge i messaggi it+en in un proprio `locale/` e li dichiara nel suo `AppModule`.
- **Paginazione**: gli adapter ricevono i `*PageParams` (`page, pageSize, orderBy, search`, `zoneId`) e
  restituiscono `PaginatedResponse[Dto]`; ordine di default per vnum; `search` su `PageParams.search_fields`.
- **Enum**: i DTO usano le enum `pachimud.*` (valori interi: direzioni, settori, door flag, tipi di reset,
  ...). Un adapter su file mappa i propri valori su queste.
- **Scritture**: ogni metodo che scrive chiama un controllo `read_only` (409 `world.read_only`); il router
  usa `WriteAdapterDep` che lo fa prima, l'adapter e' l'ultima difesa.

## Estensioni additive dei DTO (per i MUD che ne hanno bisogno)

Introdotte con Diku Modificato, tutte opzionali: gli adapter che non le usano (pachimud) le lasciano `null`/`{}` e **rifiutano** valori in
ingresso (422 `world.extra_unsupported`).

- `ResetCommandOut/In/Draft`: `ifValue: int|null` (l'`if_flag` intero: in Diku Modificato `> 0` condizionato, `<= 0` sempre, anche `-5`;
  `ifFlag` resta il booleano `> 0`), `comment: string|null` (commento della riga), `extra` (Diku Modificato: `letter`, `missingArg4`).
- `commandType` e' `ZoneCommandType | int`: oltre ai 7 tipi ROM esistono gli interi **7 charm (`C`), 8 odio (`H`), 9 paura
  (`F`), 10 zona del mob (`Z`)** (`common.adapters.models.EXTENDED_COMMAND_TYPES`, costanti in `rules`: `CHARM_MOB`,
  `SET_HATE`, `SET_FEAR`, `SET_MOB_ZONE`; `validate_script` li conosce). Altri interi: 422.
- `ExitOut.extra` e `ExitPatch.extra` (Diku Modificato: `exitInfo` grezzo, `openCmd`, `dState`).
- Il frontend deve leggere `GET /api/meta/enums` del mondo (`zoneCommandType` e le tabelle `dikumod*`/`rom*`) invece di assumere
  le enum di pachimud.

## Regole riusabili (`common/adapters/rules.py`)

Un nuovo adapter non riscrive la logica di integrita': la riusa passando un piccolo "lookup".

- Script di reset: `validate_script(lookup, comandi)` con `ResetLookup` (`existing_vnums(kind, vnums)`,
  `exit_has_door(room_vnum, direction)`); poi `to_issues` (endpoint validate) o `raise_script_errors`
  (replace). `structural_problems` e' la validazione per comando.
- Uscite: `check_exit(room_id, final, touched, key_exists)`.
- Zone: `check_zone_ranges`, `suggest_zone_range`, `range_clash`, `first_free_vnum`.
- Uso: `USAGE_FIELDS` (quali argomenti dei reset contengono un vnum) e `raise_if_used(usage, code)`.
- Grafo: `build_room_graph(GraphRoom[], GraphExit[])`.

# Capability (`AdapterCapabilities`)

| Flag | Significato | Effetto |
|---|---|---|
| `read_only` | ogni scrittura rifiutata | 409 `world.read_only` |
| `supports_world_overview` | panoramica/grafo zone/ricerca (`/api/world`) | senza: 409 `world.capability_missing` |
| `supports_instances` | istanze vive (`/api/instances`) | idem |
| `supports_players` | account/personaggi/inventario (`/api/players`) | idem |
| `supports_transfer` | `export_zone_bundle` / `import_zone_dir` (`/api/transfer`) | idem |
| `supports_content_races` | razze/classi YAML (`/api/content`) | idem |
| `supports_reset_scripts` | script di reset modificabile (default vero) | informativa per il frontend |
| `supports_extra_descriptions` | extra description sulle stanze (default vero) | informativa per il frontend |

I moduli opzionali (`world`, `instances`, `players`, `transfer`, `content`) sono specifici del mondo pachimud: si
registrano se e' configurato un mondo `kind: pachimud` e lavorano sul database del mondo **scelto dalla richiesta**
(`X-World`), non su una sessione globale (`pachimudeditor_adapter_pachimud/editor/db.py`: `SessionDep` apre una sessione dell'adapter attivo;
409 `world.not_pachimud` se il mondo attivo e' di un altro tipo). I loro router hanno una dipendenza
`require_capability(...)`: su un mondo che non la dichiara rispondono **409 `world.capability_missing`**.
Trasferimento: `export_zone_bundle`/`import_zone_dir` sono implementati da `PachimudAdapter` (`pachimudeditor_adapter_pachimud/transfer/`);
il router (`pachimudeditor_adapter_pachimud/apps/transfer`) fa solo lo staging dei file caricati.

# Come scrivere un nuovo adapter (checklist)

1. Crea il pacchetto `adapters/<nome>/` (vedi "Scrivere un adapter esterno") con `adapter.py`: una classe che estende `WorldAdapter` e implementa tutti i
   metodi astratti (o compone mixin per area come `PachimudAdapter`).
2. `capabilities()`: dichiara solo cio' che funziona davvero; `describe()`: id/kind/nome e i campi delle
   risorse (`describe_resource(...)` li ricava dai DTO, oppure costruisci `FieldDescriptor` a mano).
3. Scegli la semantica di `id` (file: `id == vnum`) e documentala nel modulo.
4. Riusa `rules.py` per validazione reset, uscite, range e grafo; implementa solo il lookup.
5. Usa i codici di errore esistenti (stessi 404/409/422 del contratto); i messaggi nuovi vanno in it+en e
   `uv run pachifast locale check` deve passare.
6. Scritture atomiche e sicure su file (scrivi su temporaneo + rename; un solo scrittore per volta);
   rispetta `config.read_only`.
7. Dichiara il plugin (`plugin.py` + entry point `pachimudeditor.adapters`, vedi [Come funziona la scoperta](#come-funziona-la-scoperta)).
8. Aggiungi l'adapter a `ADAPTER_FACTORIES` in `tests/adapter_contract/conftest.py` (nel monorepo): la suite di contratto
   deve passare per intero (la factory deve restituire un mondo **pulito e scrivibile**, es. una cartella
   temporanea). Aggiungi test specifici solo per cio' che e' proprio del MUD.
9. Documenta i campi `extra` che l'adapter usa.

# Test

```bash
uv run pytest tests/adapter_contract tests/test_adapters.py
```

La suite di contratto (`tests/adapter_contract/`) parla solo con l'interfaccia: crea tutto da se' (zone,
stanze, mob, oggetti con i vnum suggeriti da `next_*_vnum`), verifica CRUD, paginazione/ricerca/filtri,
clonazione, uso nei reset, blocchi di cancellazione/cambio vnum, validazione dei reset e le funzioni
opzionali coerenti con le capability dichiarate.


# Punti aperti per un adapter su file

- `id` di uscite/extra description (non hanno vnum) e di `ResetCommandOut` (indice nello script).
- Le enum sono quelle di pachimud (copie in `common/enums.py`, allineate al gioco da `tests/test_game_compat.py`): i flag specifici del MUD (stanze/mob/oggetti) viaggiano come `list[str]`.
- Ordine/formattazione dei file: scrivere in modo da minimizzare i diff; preservare le sezioni non
  modellate (candidato naturale: `extra` o conservazione del testo grezzo).
- `delete_*` e cambio vnum: su file non esistono FK, l'integrita' e' tutta in `rules.py`/nell'adapter.
- Istanze vive, giocatori e panoramica del mondo non hanno equivalente: capability a `False`.
- Concorrenza: piu' richieste su uno stesso file `.are` richiedono un lock per file.
