# Famiglie di adapter

Un **adapter** è l'oggetto che sa dove vivono i dati di un mondo (un MUD) e li espone all'editor con la stessa interfaccia,
[`WorldAdapter`](index.md). Il resto dell'editor (rotte, frontend, conversione tra mondi) non sa e non deve sapere se i dati stanno in un
database o in un file: per questo la documentazione descrive gli adapter per **famiglia**, non per MUD. I MUD sono solo gli esempi.

Le famiglie sono tre, e si distinguono per **dove sta la fonte di verità** e **chi conosce il formato**:

| Famiglia | I dati stanno in | Chi conosce il formato | Esempi | `kind` |
|---|---|---|---|---|
| [FileBased](#filebased) | file del MUD (aree, file dati, YAML) | codice Python dell'adapter, spesso con una libreria standalone | Diku Modificato, basedmud / ROM 2.4, pachimud (contenuti YAML) | `dikumod`, `basedmud`, `pachimud` |
| [DatabaseBased](#databasebased) | un database (SQLAlchemy) | lo schema del database, letto al volo | nessun adapter attuale (pachimud lo usa solo per account e personaggi) | - |
| [Mapped](#mapped) | file del MUD | un **file YAML di mappatura**, nessun codice | tbaMUD e altri MUD a token (non provato) | `mapping` |

Quale scegliere per un MUD nuovo: se i dati sono in un database, DatabaseBased. Se sono in file di un formato a token della
famiglia Diku/ROM, provare prima Mapped (basta un YAML); se il formato è binario, ha regole speciali o la mappatura non lo esprime,
FileBased con un adapter scritto in Python.

!!! note "Mapped è FileBased dichiarativo"
    Tecnicamente un adapter Mapped legge e scrive file come un FileBased: cambia come si descrive il formato (un YAML al posto
    del codice). Per questo condivide con la famiglia FileBased i servizi di base (paginazione in memoria, regole di integrità,
    scrittura atomica, sola lettura) e le sue avvertenze sul server acceso.

## Cosa hanno in comune

Tutte le famiglie realizzano la stessa interfaccia e lo stesso contratto ([contratto API](../backend/contract.md)):

- il **nucleo** (zone, stanze, mob, oggetti, script di reset, extra description, uscite) con DTO neutri camelCase
  ([`common/adapters/models.py`](index.md#struttura)); nessun tipo SQLAlchemy o struttura di file attraversa l'interfaccia;
- le **regole di integrità** indipendenti dal backend dati ([`common/adapters/rules.py`](index.md#struttura)): validazione degli script
  di reset, coerenza delle uscite, range di zone, vnum liberi, uso nei reset, grafo delle stanze;
- le **capability** ([`AdapterCapabilities`](sdk.md)): ciò che un adapter sa fare oltre al nucleo (panoramica, istanze vive, giocatori,
  trasferimento di zone, canale live, ...) è dichiarato, mai presunto; senza capability la rotta risponde 409
  `world.capability_missing`;
- la **sola lettura** (`read_only` nel mondo): ogni scrittura è rifiutata con 409 `world.read_only`, anche dall'adapter stesso;
- la **conversione** tra mondi ([conversione](../conversion.md)): ogni adapter porta il proprio "sapore" e l'editor compone i due.

## FileBased

I dati sono file del MUD (`.are`, `dikumoddata.wld`, ...). L'adapter ha un **store** che legge, indicizza e riscrive quei file.

**Come funziona**

- `id == vnum`: nello stesso mondo il vnum è l'identità stabile di stanze, mob e oggetti (gli id restano opachi per il client).
- La libreria di lettura/scrittura del formato (`rom_lib`, `dikumod_lib`) è **standalone**: non dipende dall'editor, ha i suoi test e
  può essere usata da sola.
- Lo store tiene una cache invalidata da `(mtime, size)` e gli indici per vnum; la paginazione, la ricerca e l'ordinamento sono in
  memoria (`common/adapters/paging.py`).
- La scrittura è **atomica** (file temporaneo + `replace`, con i permessi del file originale) e conservativa: gli elementi non
  modificati restano **byte per byte** uguali, quelli nuovi o cambiati sono riscritti nella forma canonica del MUD.
- Le tabelle del MUD (flag, settori, tipi di oggetto) diventano le enum di `GET /api/meta/enums`.

**Pro e limiti**

- Nessun servizio da avviare: basta la cartella dei dati. La sola lettura è un'ottima modalità di prova.
- Nessun database e nessuna transazione: due scrittori sullo stesso file (l'editor e il gioco) non si coordinano. Con il server
  acceso il gioco può riscrivere i file che l'editor ha appena cambiato; le zone si rileggono solo al riavvio.
- Ogni formato è un'implementazione a sé (parser, writer, mapping verso i DTO, enum).

**Estensioni tipiche della famiglia** (opzionali, dichiarate con capability)

- [giocatori su file](../backend/contract-players-files.md): elenco, dettaglio, inventario e, se l'adapter lo sa, modifica
  (`PlayersAdapter`);
- [canale di controllo live](../backend/live-control-protocol.md): per modificare al volo un MUD acceso senza passare dai file
  (`LiveAdapter`, un piccolo modulo nel MUD).

**Adapter:** [dikumod](dikumod.md) (Diku Modificato), [basedmud](basedmud.md) (ROM 2.4 / QuickMUD / basedmud) e [pachimud](pachimud.md) (contenuti in YAML, `id == vnum`).

## DatabaseBased

I dati sono righe di un database di gioco, aperto con SQLAlchemy. L'adapter **non importa** il codice del MUD: legge lo schema
reale al volo (riflessione) e lo confronta con le revisioni note.

**Come funziona**

- `id` è la **chiave primaria** della riga (opaca per il client).
- La connessione, il dialetto (SQLite o altro driver async) e i percorsi accessori (`definitions/`) stanno nei `params` del mondo.
- Le scritture sono **transazioni** del database: coerenza e isolamento sono quelli del motore, non dell'adapter.
- All'apertura si controlla lo schema (revisione delle migrazioni, colonne attese) e si segnalano i disallineamenti con uno
  stato (`ok`, `behind`, `unknown`, `unversioned`, `incompatible`): si avvisa, non si altera mai lo schema del gioco.
- Il database **dell'editor** (utenti, opzioni) è sempre separato da quelli dei MUD.

**Pro e limiti**

- Transazioni, vincoli e query vere: ricerca globale, uso nei reset e grafo tra zone sono interrogazioni, non scansioni.
- È l'unica famiglia che si presta alle entità "vive" del gioco (account, personaggi, istanze di mob e oggetti), esposte con
  capability dedicate (`supports_players`; `supports_instances` per i mondi che le hanno).
- Dipende dallo schema del MUD: quando il gioco cambia schema bisogna riallineare i modelli e le revisioni note
  ([contribuire](../contributing.md)).
- Il gioco può tenere i dati in memoria: una modifica al database non è vista finché il server non ricarica.

**Estensioni tipiche:** istanze vive, giocatori e account, trasferimento di zone (cartella YAML di scambio), razze e classi.

**Adapter:** nessuno dedicato. [pachimud](pachimud.md) fino al commit `e958b4e` del gioco teneva nel database anche i contenuti; ora ha
contenuti su file YAML (famiglia FileBased) e usa questo meccanismo (riflessione, controllo dello schema) solo per le tabelle `account` e
`player_character`.

## Mapped

Un adapter **unico** (`MappingAdapter`) legge e scrive file di MUD qualsiasi, guidato da un **YAML di mappatura** che descrive i
record (campi, sezioni, tabelle) e come si traducono nei DTO neutri. Non c'è codice da scrivere per i formati a token della
famiglia Diku/ROM.

**Come funziona**

- Il YAML è validato al caricamento (struttura, campi, espressioni, enum), con tutti gli errori insieme e `file:riga`; esiste
  uno schema JSON per l'autocompletamento.
- Una grammatica dichiarativa legge i record; le espressioni sono sicure (lista bianca, niente `eval`); per le eccezioni ci sono
  gli **hook** in codice (`field`, `record`, `zone_range`).
- Convenzioni come FileBased: `id == vnum`, cache per `(mtime, size)`, scrittura atomica con record invariati byte per byte.
- Gli esempi inclusi sono `rom.yaml`, `diku_classic.yaml` e `minimud/`.

**Pro e limiti**

- Aggiungere un MUD è questione di scrivere un YAML (anche in modo iterativo, con la validazione che indica gli errori).
- Si può esprimere solo ciò che la grammatica sa descrivere: formati binari, strutture con riferimenti complessi o regole
  particolari richiedono un hook o un adapter FileBased vero e proprio.
- Nelle capability copre il nucleo (zone, stanze, mob, oggetti, reset); giocatori su file e canale live non ci sono.
- tbaMUD è il candidato naturale della famiglia, ma **non è stato provato**: non c'è una mappatura inclusa per tbaMUD.

**Adapter:** [mapping](mapping.md); guida alla scrittura di un YAML in [guida alla mappatura](mapping-guide.md).

## Confronto

| | FileBased | DatabaseBased | Mapped |
|---|---|---|---|
| Fonte di verità | file del MUD | database | file del MUD |
| Parametro principale del mondo | `path` | `params.database_url` | `path` + `mapping` |
| `id` delle entità | vnum | chiave primaria | vnum |
| Formato descritto da | codice Python (+ libreria) | schema del database (riflessione) | YAML di mappatura |
| Scrittura | file atomico, byte per byte | transazione | file atomico, byte per byte |
| Concorrenza col gioco | nessuna (il gioco può sovrascrivere) | quella del motore | nessuna (il gioco può sovrascrivere) |
| Controlli all'avvio | esistenza e lettura dei file | revisione e colonne dello schema | validazione del YAML |
| Giocatori, istanze, trasferimento | giocatori su file e canale live (dikumod) | account, personaggi, istanze, trasferimento | non previsti |
| Nuovo MUD | scrivere un adapter | scrivere un adapter | scrivere un YAML |
| Esempi | dikumod, basedmud | pachimud | mapping (tbaMUD: non provato) |

## Scrivere un adapter

Qualunque sia la famiglia, un adapter è un pacchetto con un `plugin` scoperto tramite entry point: vedi [SDK e adapter
esterni](sdk.md). Il mixin e gli helper di partenza dipendono dalla famiglia: per i file si parte da `paging`, `rules` e dalla
scrittura atomica dell'SDK; per un database da una sessione per mondo, dalla riflessione e dalle regole condivise; per un nuovo MUD a token
Diku/ROM si prova prima con la mappatura.
