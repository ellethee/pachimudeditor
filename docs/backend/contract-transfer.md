# Contratto backend: transfer (esporta/importa zone)

Prefisso `/api/transfer`. Stesse convenzioni di [contratto API](contract.md) (auth Bearer, envelope, camelCase, errori `{detail:[{loc,msg,code,params}]}`).
Il formato dei file e' esattamente quello letto da `pachimud.zone.importer.import_zone_directory`
(`zone.yaml`, `rooms.yaml`, `mobs.yaml`, `objects.yaml`, `resets.yaml`): enum scritti per **nome** (non interi),
dadi `XdY+Z`, uscite come dict per direzione (`north`, ...), campi `None` omessi. `zone_id` e' ricavato dal nome
(slug) perche' il DB non lo memorizza. Round-trip verificato dai test (esporta -> importa in DB vuoto -> riesporta: testi identici).

## Esportazione
- `GET /transfer/zones/{id}/export` -> **zip** (`application/zip`, `Content-Disposition: attachment`, **senza envelope**) con `<slug>/{zone,rooms,mobs,objects,resets}.yaml`. 404 `transfer.zone_not_found`.
- `GET /transfer/zones/{id}/export/bundle` -> `{zoneVnum, zoneName, folder, files: {"zone.yaml": "<testo>", ...}, warnings: string[]}`; `warnings` elenca eventuali incoerenze dei dati del DB rispetto agli schemi `Loader*`.

## Importazione
`POST /transfer/zones/import` — `multipart/form-data`, campo ripetibile `files`: uno zip e/o i file yaml sciolti
(`zone.yaml` obbligatorio). Query:
- `dryRun` (default `true`): solo anteprima, **non scrive nulla**.
- `confirm` (default `false`): per l'import vero servono `dryRun=false` **e** `confirm=true` (altrimenti 422 `transfer.confirm_required`).

Risposta `ImportPreview`:
```
{ zone: {vnum,name,action}, rooms|mobs|objects: {create,update,unchanged,items:[{vnum,name,action}],keptNotInFile:[vnum]},
  resets: {inFile,inDb,changed}, warnings: [{code,params}], conflicts: [{kind,vnum,zoneVnum,zoneName}], applied: bool }
```
`action` = `create` | `update` | `unchanged` (confronto con il DB dopo normalizzazione con gli schemi del gioco).
Semantica dell'importer: upsert per vnum, **mai cancellazioni** (`keptNotInFile`), reset ed extra description sostituiti per intero.
`warnings[].code`: `out_of_range`, `invalid_range`, `dangling_exit`, `unknown_reset_ref`, `unknown_key`, `unknown_race`, `unknown_class`, `range_overlap`.

Errori: 422 `transfer.no_files|unsupported_file|invalid_archive|zone_missing|multiple_zones|invalid_file|confirm_required`,
413 `transfer.file_too_large` (20 MB totali per upload su tutti i file e zip, 2 MB per ogni YAML), 422 `transfer.invalid_archive` anche oltre 10 file o 200 voci per upload, 422 `transfer.invalid_file` oltre 5000 record per file, 422 `world.value_out_of_range` per id/page/vnum oltre i limiti degli interi, 409 `transfer.vnum_conflict` (import vero con vnum che appartengono ad altre zone; in dry-run sono in `conflicts`).
Sicurezza upload: dello zip si usa solo il nome base dei 5 file ammessi (nessuna scrittura da path dell'archivio), estrazione in cartella temporanea.
