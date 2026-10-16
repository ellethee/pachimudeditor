# dikumod_lib (pachimudeditor_adapter_dikumod.dikumod_lib)

Libreria Python standalone (solo stdlib, nessun import di pachimud) per leggere e scrivere i file dati di **Diku Modificato**
(un Diku molto modificato). Fonte di verita' del formato: il caricatore del gioco (`db.c`, `shop.c`, `utility.c`) e il documento `docs/formats/dikumod.md` (dove i documenti e il codice divergono
vale il codice).

```python
from pachimudeditor_adapter_dikumod.dikumod_lib import load_world, save

world = load_world("/percorso/a/dikumod2")     # la cartella lib/ oppure la sua radice
mob = world.mob.find(3000)                                # entita' interpretata oppure `Raw` (record corrotto)
mob.level = 30
save(world.mob)                                           # atomico; cambia solo il record toccato
```

## Cosa legge

| File | Modello | Note |
|---|---|---|
| `dikumoddata.wld`, `rooms/<vnum>` | `Room` (`Exit`, `ExtraDesc`, `Tele`, fiume, `moblim`, `L`) | guidato dai token come `load_one_room` |
| `dikumoddata.mob` | `Mob` (tipi `S A N B L`) | record = da `#` a inizio riga fino al prossimo `#`/`%%` |
| `dikumoddata.obj`, `objects/<vnum>` | `Obj` (`E`*, `A`* max 5, `P`) | idem; nei file per-vnum l'identita' e' il nome del file |
| `dikumoddata.zon`, `zones/<n>.zon` | `Zone` / `ZoneOverride` con `ZoneCmd` (`M O G E P D C H F Z`) e `ZoneText` (commenti, righe vuote) | parser **per righe** |
| `dikumoddata.shp` | `Shop` | guidato dai token come `boot_the_shops` |
| `scripts.dat` | `ScriptEntry` | il testo di `scripts/<Nome>` e' un file di testo semplice |

Ogni file e' un `RecordFile`: `head` (prima del primo record), `items` (entita' e `Raw`), `tail` (terminatore `%%~`,
`#9999999 / $~`, resto), `diagnostics`. I file si leggono come `latin-1` (un carattere per byte: round-trip esatto).

## Tolleranza: i record corrotti non si perdono

Ogni record e' letto in isolamento con le primitive del gioco (`cscan.CScan`: `fread_string`, `fread_number`, `fscanf`,
`fgets`). Se non e' interpretabile diventa un `Raw(vnum, src, error, line)` e il parsing riprende dal record successivo.
Sui dati reali: 33 mob corrotti per variante (dado malformato, record troncato, `~` mancante, numero o lettera tipo
corrotti), 1 negozio troncato. I `Raw` si riscrivono **identici**. Dati dopo l'ultimo campo letto dal gioco in un mob (es.
`0 0 0`, stringhe di suono su un `N`) sono ignorati dal loader: stanno in `Mob.trailing` e si conservano.

`Diagnostic` (`file`, `line`, `vnum`, `message`, `severity`) elenca anche gli avvisi: settore fuori tabella (stanza 13798),
comandi di zona con argomenti mancanti o commenti oltre 79 caratteri (che il loader C rilegge come comandi), terminatore
mancante.

## Scrittura: byte-esatta dove non si tocca, canonica dove si tocca

Ogni entita' ricorda il sorgente (`_src`) e l'impronta dei campi (`_fp`):

- invariata o `Raw` -> testo originale, byte per byte (anche `a|b|c`, spazi, `\r`);
- nuova o modificata -> forma canonica (come `write_obj_to_file`/`Zwrite`/`RoomSave`): stringhe `testo~` + `\n`, numeri
  semplici (mai `|`), **sempre 5 numeri per le `O`**, `L` con il suono che inizia per `\n` come lo legge `read_mobile`;
- `write_text(rf, canonical=True)` riscrive tutto in forma canonica (idempotente);
- `RecordFile.is_clean()` dice se c'e' qualcosa da riscrivere; `save` e' atomico (temporaneo + `os.replace`).

### Vincoli del gioco che la scrittura rispetta (verificati con un'emulazione rigorosa)

1. **`.mob`/`.obj` indicizzati per righe** (`generate_indices`): una riga che inizia per `#` apre un record, una che inizia
   per `%%` chiude il file; `fgets(buf, 82)` spezza le righe lunghe a 81 caratteri e anche il **frammento** puo' iniziare
   per `#`. `index_hazard` lo rileva e il writer alza `DikumodWriteError`. Il file deve finire con `%%` (senza, il gioco va in
   `assert`): `ensure_terminator` lo aggiunge.
2. **Ordine di vnum**: `real_mobile`/`real_object` fanno una ricerca **binaria** sui record del file principale. I record
   devono restare ordinati: `insert_sorted` inserisce al posto giusto, `is_sorted` verifica. I vnum doppi esistono (mob
   3703 16053 19208 21356, oggetti 16056 16207 21361): ne trova uno solo.
3. **Zone**: `O` richiede 5 numeri (`fscanf(" %d")` per il quarto salta il newline e fallisce: il loader C legge 90 zone
   invece di 93 dal file originale). Una zona riscritta porta le sue `O` a 5 numeri (`needs_fix`); le zone non toccate
   restano identiche. Il commento di una riga e' letto con `fgets(buf, 80)`: oltre 78 caratteri viene troncato in scrittura.
4. **Stringhe**: `~` non ha escape (vietata nei testi); `fread_string` scarta il carattere dopo la `~` (si scrive `\n`);
   dopo `D<n>` il loader salta tutti gli spazi (la descrizione di un'uscita non puo' iniziare con spazi).
5. **Flag**: `fread_number` somma i termini separati da `|`; in scrittura un solo intero.

## Test e verifica

`tests/dikumod_lib/` (copie temporanee dei dati reali di `dikumod` e `dikumod2`, mai scrittura sugli originali: hash a fine
sessione):

- `c_loader.py`: re-implementazione rigorosa delle letture di `db.c` (`generate_indices`+`real_*`, `read_mobile`,
  `read_obj_from_file`, `load_one_room`, `boot_zones` con la trappola di `O`, `boot_the_shops`), indipendente dal parser;
- `test_roundtrip_real.py`: conteggi (dikumod 3841 stanze / 2093+33 mob / 2025 oggetti / 93 zone / 7832 comandi; dikumod2 3856 /
  2097+33 / 2041 / 93 / 7861), parse -> write byte-identico di tutti i file, riscrittura canonica idempotente;
- `test_loader_emulation.py`: ogni vnum raggiungibile con la ricerca binaria, parser e loader concordano su ogni campo di
  ogni mob/oggetto/stanza, 90 zone dal file originale e 93 dopo la riscrittura canonica;
- `test_mutation.py`: modifica di un solo record, inserimento ordinato, blocchi teleport/fiume/tunnel/luce, zone, testi pericolosi.

```bash
uv run pytest tests/dikumod_lib -s      # -s stampa le statistiche
```

## Limiti

- Gli script dei mob (`scripts/<Nome>`) sono testo semplice: nessun parser del linguaggio.
- `dikumoddata.gui`/`gilde/`, `world/<vnum>` (binari), `mobiles/` (vestigiale), `dikumoddata2/3/4.*` e `.err` dell'editor Windows non sono letti.
- Mob di tipo `D` (vecchio Diku, assente nei dati) e stanze con codice `C` sono trattati come `Raw`.
- I file sono letti per intero in memoria (1,4 MB il piu' grande): niente streaming.
- Non c'e' validazione semantica (riferimenti, vnum doppi): sta nell'adapter (`adapters/dikumod`).
