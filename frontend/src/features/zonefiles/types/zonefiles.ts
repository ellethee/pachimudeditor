/** Tipi dei file YAML grezzi delle zone (`/api/content/zonefiles`). */

/** Tipo di file di zona. */
export type ZoneFileKind = 'zone' | 'rooms' | 'mobs' | 'objects' | 'resets'

/** Un file di zona nell'elenco. */
export interface IZoneFileEntry {
  /** Percorso relativo a `zones/` (`ZonaAlfa/mobs.yaml`). */
  path: string
  zone: string
  name: string
  kind: ZoneFileKind
  /** Nome dello schema JSON (`GET /api/content/schemas/{name}`). */
  schemaName: string
  size: number
  etag: string
}

/** Un file di zona con il testo. */
export interface IZoneFileContent extends IZoneFileEntry {
  text: string
}

/** Una violazione di schema trovata dal backend. */
export interface IZoneFileIssue {
  field: string
  line: number | null
  message: string
}

/** Errore di salvataggio interpretato. */
export interface ISaveProblem {
  /** `yaml` (sintassi), `schema` (violazioni), `changed` (etag), `other`. */
  type: 'yaml' | 'schema' | 'changed' | 'other'
  message: string
  line?: number | undefined
  column?: number | undefined
  issues: IZoneFileIssue[]
}
