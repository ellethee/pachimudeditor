# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Il progetto è documentato in italiano (docs, commenti, docstring, messaggi): mantieni la lingua e lo stile esistenti.

## Cos'è

Editor web di MUD: backend [pachifast](https://pypi.org/project/pachifast/) (FastAPI) + frontend Quasar (Vue 3 + TS) buildato e incluso nel wheel. Monorepo uv workspace con 5 pacchetti, ciascuno con la propria versione (vedi `RELEASING.md`): il core `pachimudeditor` e gli adapter in `adapters/{pachimud,basedmud,dikumod,mapping}`. Python >= 3.14.

## Comandi

```bash
uv sync --all-packages                    # core + adapter editabili + dev group
uv run pachimudeditor init --workdir .    # la cartella del repo è anche workdir (.env, pachimudeditor.yaml, DB auth)
uv run pachimudeditor serve --workdir . --reload   # http://127.0.0.1:8123 (serve anche la SPA da src/pachimudeditor/static)

uv run pytest -q                          # suite completa (nessun dato MUD reale richiesto)
uv run pytest tests/core -q               # solo core, senza adapter
uv run pytest tests/test_zones.py::test_nome -q    # singolo test
uv run pytest -q -rs                      # elenca i test saltati col motivo
uv run ruff check . && uv run ruff format --check .   # gruppo dev "ruff": uv run --only-group ruff ruff ...

(cd frontend && pnpm install && pnpm run typecheck)   # typecheck = quasar prepare + vue-tsc
(cd frontend && pnpm dev)                              # dev server Quasar
uv run pachimudeditor build-frontend      # pnpm build + copia in src/pachimudeditor/static (git-ignored)

(cd e2e && pnpm install && pnpm test)                  # Playwright su stack isolato (porta 8124); richiede frontend buildato
(cd e2e && pnpm test tests/zones.test.ts)              # un solo file e2e

uv run --group docs mkdocs serve          # documentazione in docs/
scripts/build_package.sh [--only core|pachimud|...]    # wheel/sdist; non pubblica
```

Test sui dati reali (marker `real_rom`, `real_dikumod`) si saltano se mancano `BASEDMUD_AREA_DIR`, `DIKUMOD_ROOT`, `DIKUMOD_PREFIX`; `PACHIMUD_GAME_ROOT` abilita `tests/test_game_compat.py`. La CI fallisce se i test saltati superano `MAX_SKIPPED` in `.github/workflows/ci.yml`: aggiornalo dopo aver aggiunto/spostato test. Ruff: line-length 140, regole `D` e `ANN` attive (docstring e type hints obbligatori fuori da `tests/`); `dikumod_lib`, `rom_lib`, `frontend`, `e2e`, `migrations` sono esclusi.

## Architettura

**Core generico + adapter come plugin.** Il core (`src/pachimudeditor/`) non importa mai gli adapter (verificato da `tests/core/test_boundaries.py`): li scopre via entry point `pachimudeditor.adapters`, importando solo il modulo `plugin` di ciascuno (`AdapterPlugin` con riferimenti stringa `"modulo:attributo"`). Un kind viene caricato (factory, moduli API, regole di conversione) solo se esiste un mondo configurato di quel kind. `modules.py::build_modules(kinds)` assembla i moduli pachifast: quelli generici del core (`apps/zones, rooms, mobs, objects, meta, convert, worldplayers`) più quelli dei plugin.

**Interfaccia `WorldAdapter`** (`common/adapters/base.py`): tutto ciò che l'editor chiede a un mondo. I router in `apps/` sono sottili e delegano all'adapter attivo (`AdapterDep`/`WriteAdapterDep` in `common/adapters/registry.py`); DTO in `common/adapters/models.py` (nessun tipo SQLAlchemy attraversa l'interfaccia). Metodi/capability opzionali (zone bundle, import, giocatori, ...) rispondono 409 `world.capability_missing` se non dichiarati; un mondo `read_only` rifiuta le scritture (409 `world.read_only`). Il mondo attivo si seleziona con l'header `X-World`; l'elenco è in `/api/worlds`. API pubblica per gli adapter: `src/pachimudeditor/sdk/` (`SDK_VERSION`; rompere l'SDK = nuova minore/maggiore del core, gli adapter dichiarano `pachimudeditor>=X,<Y`).

**Adapter** (`adapters/<kind>/src/pachimudeditor_adapter_<kind>/`):
- `pachimud`: legge/scrive il DB SQLAlchemy del gioco; i modelli sono **copiati** in `game_models/` (il MUD non è una dipendenza, vedi `docs/contributing.md` per riallinearli); ha le app extra players/instances/transfer/content.
- `basedmud` (ROM 2.4/QuickMUD) e `dikumod` (Diku Modificato): file su disco, `id == vnum`, con librerie standalone di parse/format `rom_lib` / `dikumod_lib` (escluse da ruff).
- `mapping`: qualunque MUD su file descritto da un YAML di mappatura (`mapping.schema.json`, `examples/`, DSL in `dsl.py`/`grammar.py`).

**Configurazione**: priorità env > `.env` > `pachimudeditor.yaml` (YAML pachifast con chiavi `webeditor_worlds`, `webeditor_default_world`, ...) > default. Nessun mondo è implicito. Gli utenti dell'editor stanno in un DB auth **separato** nella workdir (`--workdir` > `$PACHIMUDEDITOR_WORKDIR` > cwd); le migration sono in `migrations/`.

**Conversione tra mondi**: `common/adapters/convert` compone i `flavor` dei plugin dei due mondi; endpoint con rate limit (`common/rate_limit.py`).

**Frontend** (`frontend/src/features/<feature>`): una feature per area, su `@ilpachi/pachifastquasar`; la SPA buildata finisce in `src/pachimudeditor/static` ed è servita da `spa.py`. Le pagine specifiche di un mondo compaiono solo se l'adapter dichiara la capability.

**Contratto API**: documentato in `docs/backend/` (es. `contract-players-files.md`); cambiando endpoint/DTO aggiorna anche docs, `CHANGELOG.md` (voci sotto `## Non rilasciato`) e i test e2e.

## Regole del progetto

- Package manager: `uv` per Python, `pnpm` per Node (per la pubblicazione npm).
- Test: i mondi sintetici stanno in `tests/support/synthetic_worlds.py`; `tests/conftest.py` salta in raccolta tutto tranne `tests/core` se non sono installati tutti gli adapter.
- Versioni solo nei `pyproject.toml`; tag per pacchetto `<pacchetto>-vX.Y.Z` (procedura in `RELEASING.md`).
- Il remote del progetto è su GitHub (`ellethee/pachimudeditor`).
