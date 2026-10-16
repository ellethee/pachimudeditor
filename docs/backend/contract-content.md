# Contratto backend: content (razze e classi YAML)

Prefisso `/api/content`. CRUD sui file `definitions/races/*.yaml` e `definitions/classes/*.yaml`
(cartella da `PachimudConfig.definition_path`). Validazione con gli schemi `LoaderRace`/`LoaderClass` del gioco
piu' controlli extra (nomi di flag/taglia esistenti per le razze; caratteristiche valide e senza duplicati per le classi).
Scrittura con `ruamel.yaml` round-trip (commenti e formato preservati, si toccano solo le chiavi cambiate) e atomica
(file temporaneo + `os.replace`). **Il game server legge gli YAML solo all'avvio: le modifiche valgono dopo il riavvio.**

Id: `^[a-z0-9][a-z0-9_]{0,63}$` (= nome file senza estensione; immutabile). Nei body i campi sono camelCase
(`raceId`, `mobOnly`, `affectedBy`, `maxStats`, `classId`, `attrPrime`, `attrsPriority`, `thac000`/`thac032` = `thac0_00`/`thac0_32`, ...).
In `PUT` vengono applicati solo i campi **inviati**; `null` rimuove la chiave dal file.

## Endpoint (identici per `races` e `classes`)
- `GET /content/{kind}` -> `RaceItem[]`/`ClassItem[]` (anche disattivati e file non validi: `valid=false`, `error`), ordinati per nome.
- `POST /content/{kind}` (201) body = campi del file (`raceId`/`classId`, `name`, `description` obbligatori per le razze).
- `GET /content/{kind}/{id}`; `PUT /content/{kind}/{id}` (`raceId`/`classId` nel body deve coincidere col path).
- `POST /content/{kind}/{id}/disable|enable`: rinomina `<id>.yaml` <-> `<id>.yaml.disabled` (non piu' caricato dal game server). Nota: il flag `disabled:` delle classi oggi non e' copiato da `BaseClass.load_from_yaml`, quindi non e' usato.
- `DELETE /content/{kind}/{id}` -> 204 senza envelope. **409** `content.race_in_use` / `content.class_in_use` (`id`, `count`) se dei prototipi di mob usano la razza (`race_id`) / la classe (`class_id` o `teaches_class_ids`).
- Item: campi del file + `file`, `disabled`, `mobCount`, `valid`, `error`.
- `GET /content/options` -> `{mobFlags, offensiveFlags, resistanceFlags, formFlags, partFlags, affectedByFlags, sizes, stats}` (liste di nomi).
- `GET /content/status` -> `{races, classes, lastModified}` (epoch secondi, per il banner "riavvio necessario").

Errori: 404 `content.not_found`; 409 `content.id_taken`; 422 `content.invalid_id`, `content.id_mismatch`, `content.invalid` (param `detail`); 422 Pydantic senza code per tipi errati.
