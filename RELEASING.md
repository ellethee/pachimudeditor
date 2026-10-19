# Rilasci

Cinque pacchetti, ciascuno con la **propria versione** (semver), pubblicati su PyPI dal workflow `publish-pypi.yml`:
`pachimudeditor` (core) e `pachimudeditor-adapter-pachimud`, `-basedmud`, `-dikumod`, `-mapping`.

## Regole di versionamento

- La versione di un pacchetto sta **solo** nel suo `pyproject.toml` (`pyproject.toml`, `adapters/<kind>/pyproject.toml`). Partono da `0.1.0`.
- Tag per pacchetto, annotato: `<nome-pacchetto>-vX.Y.Z`, ad esempio `pachimudeditor-v0.1.0`, `pachimudeditor-adapter-dikumod-v0.2.0`.
  Il workflow ricava pacchetto e versione dal tag e **fallisce** se non coincidono con il `pyproject.toml` di quel pacchetto.
- Compatibilita' adapter/core: ogni adapter dichiara `pachimudeditor>=X,<Y` (oggi `>=0.1.0,<0.2`) e il core espone `SDK_VERSION`
  (`pachimudeditor.sdk`). Rompere l'SDK = nuova versione maggiore del core (finche' e' 0.x: nuova minore); gli adapter
  incompatibili restano fermi sulla loro versione con il vecchio intervallo. Quando esce un core compatibile con gli adapter
  esistenti, gli adapter alzano il limite superiore con una loro release. Gli extras del core (`pachimudeditor[dikumod]`, ...)
  hanno solo il limite inferiore.
- Tra tag di pacchetti diversi non c'e' un ordine obbligatorio. Se cambia l'SDK: prima il core, poi gli adapter.
- Changelog: un solo `CHANGELOG.md`; ogni release e' una sezione `## <pacchetto> X.Y.Z - AAAA-MM-GG` (le modifiche in corso stanno sotto `## Non rilasciato`).

## Procedura di rilascio di un pacchetto

1. Sposta le voci da `## Non rilasciato` a una sezione `## <pacchetto> X.Y.Z - data` in `CHANGELOG.md`.
2. Aggiorna `version` nel `pyproject.toml` del pacchetto (e, se serve, gli intervalli `pachimudeditor>=X,<Y` degli adapter).
3. `uv lock` (alla radice del repository) e verifica: `uv run pytest -q`, `uv run --group docs mkdocs build --strict`.
4. Commit e push su `main`; attendi che la CI sia verde.
5. Tag annotato e push del tag (solo il tag del pacchetto che rilasci):

   ```bash
   git tag -a pachimudeditor-adapter-dikumod-v0.2.0 -m "pachimudeditor-adapter-dikumod 0.2.0"
   git push origin pachimudeditor-adapter-dikumod-v0.2.0
   ```

6. Il workflow `Pubblicazione su PyPI` parte: `prepare` (coerenza tag/versione/classificatore), `build` (per il core prima
   la SPA, poi `uv build`; `twine check` e controllo del contenuto del wheel), `publish-pypi`.
   Il job `publish-pypi` usa l'environment `pypi`: **approvalo** dalla pagina del run (Review deployments).
7. Verifica su `https://pypi.org/project/<pacchetto>/` e con un'installazione pulita
   (`uv tool install 'pachimudeditor[dikumod]'`, poi `pachimudeditor adapters list`).

Prova su TestPyPI: *Actions > Pubblicazione su PyPI > Run workflow* da `main`, scegliendo il pacchetto (environment `testpypi`).
La versione pubblicata e' quella del `pyproject.toml`; TestPyPI non permette di ripubblicare la stessa versione.

### Ordine core/adapter e indicizzazione

Gli adapter dipendono dal core: al **primo** rilascio pubblica prima il core, attendi che compaia su PyPI (di solito
pochi minuti; `pip index versions pachimudeditor` o la pagina del progetto) e solo dopo gli adapter. Per le release successive
vale l'ordine solo se un adapter richiede una versione del core non ancora pubblicata (ad esempio SDK nuovo).

### Se la pubblicazione fallisce a meta'

- Fallimento prima di `publish-pypi` (`prepare`/`build`): nulla e' stato caricato. Correggi, committa e sposta il tag:
  `git tag -d <tag> && git push origin :refs/tags/<tag>`, poi ricrea il tag sul nuovo commit e ripushalo.
- Fallimento o rifiuto in `publish-pypi`: rilancia il job dalla pagina del run (*Re-run failed jobs*). `uv publish` salta
  i file gia' caricati con lo stesso contenuto.
- Una versione caricata su PyPI **non si puo' riusare** anche se la si cancella: se il contenuto e' sbagliato, incrementa
  la patch (`X.Y.Z+1`) e rilascia di nuovo; se serve, "yank" della versione difettosa dalla pagina del progetto.
- Se un pacchetto di un rilascio multiplo e' uscito e un altro no, i pacchetti sono indipendenti: ripubblica solo quello mancante.

## Configurazione una tantum

### Repository GitHub

Il repository GitHub e' `ellethee/pachimudeditor` (branch `main`).
I workflow stanno in `.github/workflows/` alla radice del repository; la radice del repository e' la radice del progetto.

### Logo nei README (PyPI)

I README del core e degli adapter usano l'URL raw assoluto del logo
(`https://raw.githubusercontent.com/ellethee/pachimudeditor/main/docs/assets/logo.svg`) perche' PyPI non risolve i path relativi.

### Environment GitHub (Settings > Environments)

- `pypi`: *Required reviewers* (tu), *Deployment branches and tags* = tag che corrispondono a `pachimudeditor-v*` e `pachimudeditor-adapter-*-v*`.
- `testpypi`: solo il branch `main`.
- `github-pages`: creato da GitHub; *Deployment branches* = `main`.

### GitHub Pages

*Settings > Pages > Build and deployment > Source = GitHub Actions*. Il workflow `Documentazione pachimudeditor` pubblica
a ogni push su `main` che tocca la documentazione. Dopo il primo deploy aggiungi l'URL del sito in `[project.urls]`
(`Documentation`) dei `pyproject.toml`.

### Trusted publisher su PyPI e TestPyPI (nessun token)

Poiche' i progetti non esistono ancora, registra un **pending publisher** per ciascuno dei 5 pacchetti, su
<https://pypi.org/manage/account/publishing/> e su <https://test.pypi.org/manage/account/publishing/>:

| Campo | Valore |
| --- | --- |
| PyPI project name | `pachimudeditor`, `pachimudeditor-adapter-pachimud`, `pachimudeditor-adapter-basedmud`, `pachimudeditor-adapter-dikumod`, `pachimudeditor-adapter-mapping` |
| Owner | `ellethee` |
| Repository name | `pachimudeditor` |
| Workflow name | `publish-pypi.yml` |
| Environment name | `pypi` (su PyPI), `testpypi` (su TestPyPI) |

Il primo upload riuscito trasforma il pending publisher in un publisher normale e crea il progetto.

### Prima del primo rilascio: classificatore e licenza

- Tutti e cinque i `pyproject.toml` hanno `classifiers = ["Private :: Do Not Upload"]`: PyPI rifiuta l'upload. Il workflow **non** lo rimuove:
  il job `prepare` fallisce finche' e' presente. Per rilasciare, togli quella voce da ciascun pacchetto (lascia `classifiers = []` o aggiungi i
  classificatori veri, ad esempio `Programming Language :: Python :: 3.14`), poi `uv lock` e commit.
- Licenza: tutti e cinque i pacchetti dichiarano `license = "MIT"` (espressione SPDX) con il proprio file `LICENSE`; non serve altro.

### npm

Qui non si pubblica nulla su npm. I pacchetti `@ilpachi/*` usati dal frontend sono di un altro repository e si rilasciano da li'
(con `npm publish`, non con pnpm).

## Test e sdist degli adapter

I test degli adapter restano nella suite del monorepo (`tests/`, che usa fixture e dati condivisi con il core: spostarli in
`adapters/<kind>/tests/` sarebbe invasivo) e quindi **non** sono nelle sdist degli adapter; la sdist del core include `tests/`.
Sdist e wheel di ogni adapter sono comunque installabili e funzionanti (provato in un venv pulito: `pip install` delle sdist,
`pachimudeditor adapters list`, `pip check`); la CI esegue la suite completa dal checkout (senza il MUD pachimud: i modelli sono copiati, vedi `docs/contributing.md`).

## Verifiche in locale (senza pubblicare)

```bash
python3 scripts/release_check.py tag pachimudeditor-v0.1.0      # coerenza tag / pyproject / classificatore
scripts/build_package.sh --only dikumod /tmp/dist                    # build di un pacchetto
uvx twine check --strict /tmp/dist/*
python3 scripts/release_check.py wheel pachimudeditor-adapter-dikumod /tmp/dist
```
