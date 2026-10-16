# Guida alla mappatura: far leggere un nuovo MUD al webeditor con un file YAML

Il `MappingAdapter` (`kind: mapping`) e' un adapter generico: invece di scrivere codice Python per ogni MUD si scrive un
**file YAML** che dice dove stanno i file, com'e' fatto ogni record e a quale campo neutro dell'editor corrisponde ciascun
valore. Il motore (parser, writer, archivio con cache, regole di integrita', suite di contratto) e' sempre lo stesso.

- Codice: `adapters/mapping/src/pachimudeditor_adapter_mapping/` (un modulo per ruolo: `schema` carica/valida il YAML, `grammar` legge, `writer`
  scrive, `model` mappa record <-> DTO, `store` gestisce i file, `adapter`/`zones`/`rooms`/`prototypes` implementano
  `WorldAdapter`).
- Esempi pronti: `examples/rom.yaml` (ROM `.are`, un file per zona), `examples/diku_classic.yaml` (Diku/Diku Modificato, un file per
  tipo), `examples/minimud/` (l'esempio di questa guida).
- Schema per l'autocompletamento nell'editor: `adapters/mapping/src/pachimudeditor_adapter_mapping/mapping.schema.json`. Aggiungi in cima al YAML
  `# yaml-language-server: $schema=<percorso>/mapping.schema.json`.
- Registrazione e configurazione del mondo: vedi [l'adapter mapping](mapping.md).

```yaml
webeditor_worlds:
  - {id: mini, kind: mapping, name: MiniMUD, mapping: /percorso/minimud.yaml, path: /percorso/minimud/world, read_only: false}
```

## 1. Quando basta il YAML e quando serve un adapter a mano

Il YAML basta se il formato e' fatto di **token separati da spazi bianchi** (numeri, parole, stringhe terminate da `~`,
flag a lettere, dadi `NdT+B`), con record introdotti da un marcatore (`#vnum`, `#MOBILES`...) e terminati da una
sentinella (`#0`, `S`, `$~`, fine file). E' il caso dei Diku, Merc, ROM, SMAUG, tbaMUD e derivati. Serve codice (un hook
o un adapter a mano) per: formati con delimitatori (`a|b|c` per campo, CSV), XML/JSON, join fra file diversi (negozi per
keeper, override per-vnum), dati corrotti da risincronizzare. Vedi "Limiti" in fondo.

## 2. Passo per passo con MiniMUD

MiniMUD e' un MUD inventato: un file `.mini` per zona. I file stanno in
`adapters/mapping/src/pachimudeditor_adapter_mapping/examples/minimud/` e il test `tests/mapping/test_guide_example.py` verifica che tutto
quello che segue sia vero.

```
@zone
Foresta Oscura~
100 199 5 20            <- vnum minimo, massimo, livello minimo, massimo

@rooms
#100
Sentiero nel bosco~
Un sentiero stretto tra gli alberi.~
AB 3                    <- flag a lettere (A=dark, B=outdoor), settore
X 0 101                 <- uscita: direzione, destinazione
S                       <- fine della stanza
#101
...
#0                      <- fine della sezione

@mobs
#100
orco~
un orco~
Un orco ti guarda con aria torva.~
5 1d8+2 2d4+0 1         <- livello, dado vita, dado danno, sesso
#0

@resets
M 100 101               <- carica il mob 100 nella stanza 101
S

@end
```

### Passo 1: il layout (dove sono i file)

Un file per zona, tutti i `*.mini` di una cartella, nessun file indice. Il range di vnum e' scritto nell'intestazione:

```yaml
layout:
  mode: zone_files
  zone_file: mini                 # nome del tipo di file in `grammar.files`
  glob: "*.mini"
  new_zone: {style: zone, file: "{slug}.mini"}   # come si chiamano i file delle zone nuove
  zone_range:
    mode: fields
    bottom: {from: bottom}        # campi del record di zona
    top: {from: top}
```

Altri layout: file indice come `area.lst` (`index: {file: area.lst, comment: "#", end: "$"}`: le zone elencate sono
abilitate, le altre `enabled: false`) e `mode: type_files` (un file per tipo di record, vedi `diku_classic.yaml`).

### Passo 2: la grammatica (com'e' fatto un file)

Un **tipo di file** e' una lista di sezioni; ogni sezione ha un'intestazione, il record che contiene e come finisce.

```yaml
grammar:
  files:
    mini:
      header_prefix: "@"          # le intestazioni sono `@zone`, `@rooms`...
      end: end                    # `@end` chiude il file (il testo dopo e' conservato)
      sections:
        - {header: zone, record: zone, entity: zone, single: true}          # un solo record
        - {header: rooms, record: room, entity: room, until: {field: vnum, in: [0]}, tail: "#0\n\n"}
        - {header: resets, record: reset, entity: reset, until: {field: cmd, in: [S]}, tail: "S\n\n"}
```

`until` dice quando la sezione finisce: **dopo aver letto il campo `vnum`** se vale uno dei valori in `in` (il record `#0`
e' il terminatore, non un record). `tail` e' il testo canonico del terminatore quando va riscritto. Le sezioni che la
grammatica non descrive (`#HELPS`...) sono conservate come testo grezzo e riemesse identiche.

Poi i **record**: una lista di passi, ognuno legge un campo tipizzato. Per scrivere i campi basta `nome: tipo`:

```yaml
  records:
    room:
      key: vnum                     # il campo che identifica il record
      steps:
        - line: [{literal: "#", glue: true}, vnum: number]     # `#100` (glue = senza spazio quando si riscrive)
        - name: string_tilde                                    # fino alla `~`
        - description: string_tilde
        - line: [flags: {type: flags, table: room_flags}, sector: number]
        - tagged:                                               # elementi introdotti da una lettera
            end: S
            tags:
              X: {into: exits, inline: true, steps: [line: [door: number, to: number]]}
```

- Leggere: i token sono separati da spazi bianchi, la divisione in righe non conta (tranne `line_text` e `same_line`).
- Scrivere (record nuovi o modificati): ogni passo semplice e' una riga, `line: [...]` e' una riga sola. Un record non
  modificato viene riemesso **byte per byte** dal suo testo originale: aprire e salvare non cambia nulla.
- Un campo che non e' in nessun `extra` ne' nel DTO si perde solo se non lo descrivi: tutto cio' che e' nella grammatica
  fa il giro completo.

### Passo 3: le tabelle (numeri <-> nomi)

```yaml
tables:
  room_flags: {dark: 1, outdoor: 2, nomob: 4, safe: 8}     # nome -> bit
  sectors: [inside, city, field, forest]                    # indice = valore
```

Le tabelle collegate a un campo (`table: room_flags` sul passo) fanno comparire nomi (`["dark", "outdoor"]`) invece di
numeri nel DTO e in `extra`. Possono stare in un file (`{file: tabelle.yaml, name: room_flags}`, anche nel formato
`json/meta/*.json` di basedmud) e comparire in `GET /api/meta/enums` con `expose: nomeChiave`.

### Passo 4: il modello (da record a DTO)

Per ogni entita' si dice a quale record corrisponde e, campo per campo del DTO, da dove si legge e dove si riscrive:

```yaml
model:
  room:
    entity: room
    exits: exits                       # il campo-lista del record con le uscite
    defaults: {flags: 0, sector: 0}    # valori di una stanza nuova
    fields:
      name: {from: name}
      flags: {from: flags}             # flag con tabella -> lista di nomi
      sector_type: {from: sector, map: {0: INSIDE, 1: CITY, 2: FIELD, 3: FOREST}, unmapped: INSIDE}
      heal_rate: {const: 100, soft: true}    # il MUD non ha il campo: costante, scritture ignorate
```

Tutti i campi del DTO non elencati valgono il loro valore **neutro** (0, "", `null`, `[]`): un client che prova a scrivere
un valore diverso riceve 422 `mapping.field_unsupported`. Tutti i campi del record non consumati dal DTO finiscono in
`extra` (camelCase, riscrivibili): il round trip e' sempre completo.

### Passo 5: prova

```python
adapter = MappingAdapter(WorldConfig(id="mini", kind="mapping", mapping="minimud.yaml", path="world"))
await adapter.get_room(100)
```

Errori del YAML: si ricevono tutti insieme, con `file:riga`:

```
mappatura non valida (minimud.yaml):
  minimud.yaml:57: model.mob.fields.hp_dice_count.from: campo del record sconosciuto: 'hpx.n'
```

Poi aggiungi il mondo a `webeditor_worlds` e, se il formato ha tutto (zone, stanze, mob, oggetti, extra description,
reset), registra l'adapter in `tests/adapter_contract/conftest.py` (monorepo) (`ADAPTER_FACTORIES`): la suite di contratto deve
passare per intero. MiniMUD non ha extra description, quindi non e' nella suite (la capability e' spenta e le route
rispondono 409 `world.capability_missing`).

## 3. Riferimento

### 3.1 Layout

| Chiave | Significato |
|---|---|
| `mode` | `zone_files` (un file per zona) o `type_files` (un file per tipo di record, le zone sono record) |
| `encoding`, `newline` | `auto` = UTF-8 se valido, altrimenti latin-1 (round trip esatto); `lf`/`crlf` per forzare |
| `zone_file` | `zone_files`: tipo di file di ogni zona |
| `glob`, `index` | file candidati e file indice con i file abilitati (`index.comment`, `index.end`) |
| `files` | `type_files`: `{tipo di file: glob}` |
| `zone_range` | come si ricava il range: `fields` (`bottom`/`top` = `FieldMap` sull'intestazione), `top` (a catena: bottom = `top` precedente + 1, id = `top`), `hook` (funzione registrata) |
| `new_zone` | `style` (intestazione da usare) e `file` (modello del nome, `{slug}`) |
| `insert` | `append` (in coda alla sezione) o `by_vnum` (ordinati, per i file monolitici) |

### 3.2 Primitive dei campi

| Tipo | Legge | Note |
|---|---|---|
| `number` | intero con segno, somme `1\|4\|256` | `width` per allineare a destra in scrittura |
| `float` | decimale (`1.5`, `.001`) | |
| `word` | parola, o testo tra apici `'..'` | `quote: always` per scrivere sempre gli apici |
| `string_tilde` | testo (anche su piu' righe) fino a `~` | `lead: ws` salta tutti gli spazi iniziali (ROM), `lead: eol` conserva i rientri (Diku) |
| `line_text` | il resto della riga | `raw: true` senza `strip` (commenti) |
| `flags` | lettere `A`=1 ... `a`=2^26, cifre, somme `a\|b` | `write: letters` (ROM) o `number` (Diku); `table` per i nomi |
| `dice` | `NdT+B` come `{n, t, b}` | `tolerant: true` accetta `NdT` e `dT+B` |
| `tag` | un carattere (la lettera del comando) | |
| `enum` | un numero (`as: number`) o una parola (`as: word`) | `table` per i nomi |

Opzioni comuni: `count: N` (lista di N valori), `optional: true` (se il prossimo token non e' del tipo atteso il campo
manca; con `same_line: true` si guarda solo la riga corrente), `default` (valore dei record nuovi; con `optional` il campo
viene comunque **scritto** con quel valore: serve alle `O` di Diku Modificato, che vogliono sempre 5 numeri), `table`.

### 3.3 Blocchi

| Blocco | Uso |
|---|---|
| `line: [...]` | passi scritti sulla stessa riga |
| `literal: "#"` | token fisso (`glue: true`: nessuno spazio dopo; `optional: true`) |
| `when: "espressione"` + `then:` / `else:` | condizione sui campi gia' letti (anche in scrittura): `sector == -1`, `has_flag(flags, 256)`, `min_vnum is None` |
| `switch: campo` + `cases:` / `default:` | sceglie i passi dal valore di un campo (lettera del comando, tipo del mob) |
| `tagged:` | elementi introdotti da un tag (prefisso del prossimo token) in qualunque ordine; `into: lista` accumula dict, senza `into` sono campi scalari (`write_if`, `default`); `end: S` (terminatore) oppure `other` (finisce al primo token che non e' un tag); `end_before: ["#"]` tolleranza se manca il terminatore; `tag_field` memorizza il tag (liste con piu' tag); `ignore_case`; tag speciale `"?"` raccoglie qualunque altro token (chiavi sconosciute); `inline`/`glue` per la scrittura |

Un record puo' anche essere interamente affidato a un **hook** (`parser: nome`).

### 3.4 Modello

`FieldMap` (un campo del DTO), una sola fonte fra:

| Chiave | Significato |
|---|---|
| `from: campo.percorso` | `hit.n`, `ac.0`; flag con tabella -> lista di nomi; si riscrive allo stesso percorso |
| `expr` (+ `to`) | espressione di lettura sui campi del record; `to: {campo: espressione}` la inverte (nelle espressioni `value` e' il valore del DTO, enum come nome) |
| `map` | `{grezzo: MEMBRO_ENUM}` o nome di una tabella; `unmapped` per i valori non elencati; l'inverso usa la prima voce |
| `null_if` | valore grezzo che il DTO vede come `null` (`""`, `-1`) |
| `const` | il MUD non ha il campo; con `soft: true` le scritture sono ignorate, altrimenti 422 |
| `pairs: {list, key, value, table}` | lista di `{chiave, valore}` come dict (`affects: {nome: somma}`) |
| `hook` | funzione registrata in codice (vedi 3.6) |
| `in_extra: true` | il campo del record resta anche in `extra` (es. il settore ROM vero) |

Un patch applica **solo i campi diversi** dal valore corrente: rimandare un DTO letto non cambia un byte.

Altre sezioni: `zone` (`id: bottom|top|position`, `resets: {section|field}`, `defaults`), `room` (`exits`,
`extra_descriptions`), `exit` (`direction_field`, `target_field`, `no_target`, `key_field`, `door_state: fields|resets`,
`fields`, `defaults`), `extra_description`, `mob`, `object`, `reset` (`command_field`, `comments`, `commands: {lettera:
{type, if_flag, arg1..arg4, arg_str}}`, ogni slot e' un `FieldMap`). Con `door_state: resets` `isOpen`/`isLocked` vivono nei
reset `D` della zona (ROM); con `fields` sono campi come gli altri (bit di `exit_info` in Diku Modificato).

`extra` (`extra: {include: all|none|[campi], exclude: [campi]}`): di default tutti i campi non consumati.

### 3.5 DSL delle espressioni

Solo espressioni, parsate con `ast` e validate al caricamento (errori con riga): costanti, nomi (i campi del record,
`value`), `+ - * / // %`, `& | ^ << >> ~`, `and or not`, confronti (`== != < <= > >= in not in is is not`),
`a if c else b`, indici `x[0]`, liste/tuple/dict letterali. Nessun attributo, import, lambda, comprehension, f-string,
potenza. Un campo mancante vale `None`. Funzioni: `int str float bool len min max abs strip lower upper split join
replace startswith get int_or_none re_group re_sub has_flag set_flag`.

### 3.6 Hook

Il YAML non importa mai codice: dichiara i nomi in `hooks: [...]` e li usa; devono essere registrati in Python
(`pachimudeditor_adapter_mapping/hooks.py`): `register_field_hook(nome, read, write)` per un campo del DTO,
`register_record_hook(nome, parse, write)` per un tipo di record, `register_zone_range_hook(nome, fn)` per il range delle
zone. Inclusi: `zone_from_top`, `rom_credits_min_level/max_level/builder` (i livelli e l'autore ROM sono impacchettati in
una stringa `{ 5 35 } Autore Titolo`).

### 3.7 Regole e meta

`rules`: `vnum_range_check` (un vnum nuovo deve stare nel range della zona), `zone_alignment` (i range suggeriti partono da
un multiplo), `exit_id_stride`, `extra_id_stride` (id uscite/extra = `vnum * stride + posizione`). `meta`: `races`/`classes`
come lista di nomi o nome di una tabella.

## 4. Esempi inclusi e cosa dimostrano

- **`rom.yaml`** descrive i file `.are` di ROM/basedmud. `tests/mapping/test_rom_equivalence.py`: stessi record e campi di
  `pachimudeditor_adapter_basedmud.rom_lib` su tutte le aree reali, riscrittura byte per byte, un mob modificato riscrive solo il suo blocco,
  stessi DTO e stessi file del `BasedMudAdapter`.
- **`diku_classic.yaml`** descrive i file `dikumoddata.*` di Diku Modificato (un file per tipo, zone a catena su `top`). `tests/mapping/
  test_diku_classic.py` su un mondo sintetico fatto di record reali di Diku Modificato.
- **`minimud/`**: questa guida.

## 5. Limiti rispetto a un adapter scritto a mano

- **Dati corrotti**: la grammatica e' rigorosa. Un record malformato e' un errore con riga e colonna, non un blocco "grezzo"
  da saltare: i file interi `dikumoddata.mob`/`dikumoddata.shp` di Diku Modificato (record corrotti, negozi troncati) non si leggono; servirebbe un
  hook di risincronizzazione.
- **Join fra file e sezioni collegate**: negozi e spec_fun di ROM (sezioni `#SHOPS`/`#SPECIALS` legate al mob per vnum) non
  seguono il mob quando cambia vnum o viene eliminato; gli override per-vnum di Diku Modificato (`rooms/<vnum>`, `objects/<vnum>`) non
  esistono. Sono parsati e conservati, non esposti.
- **Formati non a token**: delimitatori per campo, XML, JSON, ordine libero con valori multiriga: solo con un hook di record.
- **Comandi di reset senza tipo neutro** (Diku Modificato `C H F Z`): restano nel file ma non sono elencati, e sostituire lo script di
  quella zona e' rifiutato (422 `mapping.reset_unmapped_commands`) per non cancellarli.
- **Semantica per tipo** (valori `v0-v4` di un oggetto, hit point dei mob Diku Modificato `S` vs `A/N/B/L`): solo con `expr`; i valori
  a lettere/nomi sono letti come `null`.
- **`type_files`**: una zona nuova va solo in coda; niente clonazione, niente `enabled`; `bottomVnum` e' derivato dalla zona
  precedente; spostare `topVnum` e' possibile solo se non sposta entita' fra zone.
- **Enum**: i DTO usano le enum di pachimud; i valori del MUD senza equivalente sono approssimati con `map`/`unmapped` (il
  valore vero resta in `extra` con `in_extra`).
- **Concorrenza**: un solo scrittore per volta, nessuna transazione fra piu' file; modifiche esterne concorrenti non sono
  rilevate fino alla scrittura successiva (come per gli altri adapter su file).
