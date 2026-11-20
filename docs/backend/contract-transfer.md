# Contratto backend: transfer (esporta/importa zone)

Prefisso `/api/transfer`. Stesse convenzioni di [contratto API](contract.md) (auth Bearer, envelope, camelCase, errori `{detail:[{loc,msg,code,params}]}`).
Il formato dei file e' quello della cartella di zona del gioco pachimud (`definitions/zones/<Zona>/`: `zone.yaml`, `rooms*.yaml`,
`mobs*.yaml`, `objects*.yaml`, `resets*.yaml`; enum per **nome**, dadi `XdY+Z`, uscite come dict per direzione, reset annidati).
L'esportazione restituisce i file cosi' come sono su disco (commenti inclusi); l'importazione li valida con i loader del gioco
(copie in `loaders.py`). Round-trip verificato dai test (esporta -> importa in un mondo senza zone -> riesporta: testi identici).

## Esportazione
- `GET /transfer/zones/{id}/export` -> **zip** (`application/zip`, `Content-Disposition: attachment`, **senza envelope**) con `<cartella>/<file>.yaml` per ogni file YAML della zona. 404 `transfer.zone_not_found`.
- `GET /transfer/zones/{id}/export/bundle` -> `{zoneVnum, zoneName, folder, files: {"zone.yaml": "<testo>", ...}, warnings: string[]}`; `warnings` elenca i file o le voci della zona che non si sono potuti leggere.

## Importazione
`POST /transfer/zones/import` — `multipart/form-data`, campo ripetibile `files`: uno zip e/o i file yaml sciolti
(`zone.yaml` obbligatorio; ammessi `zone.yaml` e i file `room*/mob*/obj*/reset*.yaml`). Query:
- `dryRun` (default `true`): solo anteprima, **non scrive nulla**.
- `confirm` (default `false`): per l'import vero servono `dryRun=false` **e** `confirm=true` (altrimenti 422 `transfer.confirm_required`).

Risposta `ImportPreview`:
```
{ zone: {vnum,name,action}, rooms|mobs|objects: {create,update,unchanged,items:[{vnum,name,action}],keptNotInFile:[vnum]},
  resets: {inFile,inDb,changed}, warnings: [{code,params}], conflicts: [{kind,vnum,zoneVnum,zoneName}], applied: bool }
```
`action` = `create` | `update` | `unchanged` (confronto con le voci dei file del mondo dopo normalizzazione con i loader del gioco).
Semantica dell'importer: zona nuova (vnum non presente) = i file sono copiati cosi' come sono in una nuova cartella; zona esistente = upsert per vnum nei suoi file, **mai cancellazioni** (`keptNotInFile`), script di reset sostituito per intero.
`warnings[].code`: `out_of_range`, `invalid_range`, `dangling_exit`, `unknown_reset_ref`, `unknown_key`, `unknown_race`, `unknown_class`, `range_overlap`.

Errori: 422 `transfer.no_files|unsupported_file|invalid_archive|zone_missing|multiple_zones|invalid_file|confirm_required`,
413 `transfer.file_too_large` (20 MB totali per upload su tutti i file e zip, 2 MB per ogni YAML), 422 `transfer.invalid_archive` anche oltre 10 file o 200 voci per upload, 422 `transfer.invalid_file` 422 `world.value_out_of_range` per id/page/vnum oltre i limiti degli interi, 409 `transfer.vnum_conflict` (import vero con vnum che appartengono ad altre zone; in dry-run sono in `conflicts`).
Sicurezza upload: dello zip si usa solo il nome base dei file ammessi (nessuna scrittura da path dell'archivio), estrazione in cartella temporanea.
