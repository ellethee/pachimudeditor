/** Tipi dei contenuti a strati (skill, tabelle, social, cataloghi, testi) e del canale live dei contenuti (`/api/content`, `/api/world/live/content`). */

/** Strato di un file: `user` = modificato qui (`definitions_path`), `base` = contenuti di serie del gioco (sola lettura). */
export type ContentLayer = 'user' | 'base'

/** Area dei file di testo modificabili. */
export type FileArea = 'tables' | 'locales' | 'texts'

/** Un file di contenuti (`GET /api/content/files/{area}`). */
export interface IFileEntry {
  path: string
  layer: ContentLayer
  size: number
}

/** Il testo di un file (`GET /api/content/files/{area}/{path}`). */
export interface IFileContent {
  path: string
  layer: ContentLayer
  text: string
}

/** Una skill (incantesimo o abilità): campi semplici e `advanced` (YAML degli altri campi). */
export interface ISkill {
  skillId: string
  layer: ContentLayer
  kind?: string
  name?: string
  description?: string
  disabled?: boolean
  mana?: number
  beats?: number
  fail?: number
  minPosition?: string
  violent?: boolean
  maxLearn?: number
  saving?: string
  element?: string
  targets?: string[]
  /** Dove può stare l'incantesimo; assente = nessun vincolo, lista vuota = in nessun oggetto. */
  itemTypes?: string[] | null
  /** Nome mostrato ai giocatori per lingua (`messages.name`), a sola lettura. */
  names?: Record<string, string>
  levels?: Record<string, number>
  advanced?: string
  /** Il file non si legge: solo id e messaggio. */
  error?: string | null
}

/** Un social: testi per lingua con le chiavi `noArg`, `found`, ... (sul filo restano `no_arg`, `found`, ...). */
export interface ISocial {
  name: string
  layer: ContentLayer
  aliases: string[]
  position: string
  victimMinPosition: number
  hide: boolean
  messages: Record<string, Record<string, string>>
}

/** Un problema dei contenuti (`content.validate`, `content.reload`). */
export interface IContentIssue {
  severity: 'error' | 'warning'
  code: string
  message: string
  file: string | null
  line: number | null
}

/** Esito di `GET /api/world/live/content/validate`. */
export interface IContentValidate {
  ok: boolean
  errors: number
  warnings: number
  issues: IContentIssue[]
}

/** Cosa rilegge `content.reload`. */
export type ReloadKind = 'races' | 'classes' | 'skills' | 'tables' | 'socials' | 'locales' | 'all'

/** Esito di `POST /api/world/live/content/reload`. */
export interface IContentReload {
  ok: boolean
  kind: string
  reloaded: Record<string, string[]>
}

/** Dove cade un `file:riga` di un problema (`POST /api/content/checks/locate`). */
export interface ILocated {
  /** `zone` = `zone.yaml`; `resets` = file dei reset; `file` = file senza una voce precisa; `none` = file sconosciuto all'editor. */
  kind: 'zone' | 'room' | 'mob' | 'object' | 'resets' | 'file' | 'none'
  vnum: number | null
  zoneId: number | null
}

/** Soglie del lint di stile (`GET /api/content/checks/style`). */
export interface IStyleLimits {
  enabled: boolean
  roomNameMax: number
  descriptionMinLines: number
  descriptionMaxLines: number
  descriptionWidth: number
  shortMax: number
  longMax: number
  timeWords: string[]
}
