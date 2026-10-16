/** Una zona dell'elenco `GET /api/zones` (campi usati dalla pagina). */
export interface IZoneRef {
  id: number
  vnum: number
  name: string
}

/** Azione che l'import compirebbe su un elemento. */
export type ImportAction = 'create' | 'update' | 'unchanged'

/** Un elemento del file con l'azione prevista. */
export interface IVnumChange {
  vnum: number
  name: string
  action: ImportAction
}

/** Riepilogo per tipo di contenuto (stanze, mob, oggetti). */
export interface IKindDiff {
  create: number
  update: number
  unchanged: number
  items: IVnumChange[]
  /** Vnum presenti nella zona nel DB ma assenti dai file: l'import non li cancella mai. */
  keptNotInFile: number[]
}

/** Riepilogo dei reset (sostituiti per intero). */
export interface IResetDiff {
  inFile: number
  inDb: number
  changed: boolean
}

/** Segnalazione non bloccante (`code` + `params` tradotti con `transfer.warnings.<code>`). */
export interface IImportWarning {
  code: string
  params: Record<string, string | number>
}

/** Vnum del file che nel DB appartiene a un'altra zona (blocca l'import vero). */
export interface IImportConflict {
  kind: string
  vnum: number
  zoneVnum: number
  zoneName: string
}

/** Esito dell'anteprima (o dell'import eseguito, con `applied`). */
export interface IImportPreview {
  zone: IVnumChange
  rooms: IKindDiff
  mobs: IKindDiff
  objects: IKindDiff
  resets: IResetDiff
  warnings: IImportWarning[]
  conflicts: IImportConflict[]
  applied: boolean
}
