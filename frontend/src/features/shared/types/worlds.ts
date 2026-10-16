/** Tipi del selettore di mondo: `GET /api/worlds` (vedi `docs/adapters/index.md`). */

/** Capability di un mondo (camelCase come da contratto). */
export interface IWorldCapabilities {
  readOnly: boolean
  supportsWorldOverview: boolean
  supportsInstances: boolean
  supportsPlayers: boolean
  supportsTransfer: boolean
  supportsContentRaces: boolean
  supportsResetScripts: boolean
  supportsExtraDescriptions: boolean
}

/** Nome di una capability che abilita una funzione (esclude `readOnly`, che non e' una funzione). */
export type WorldCapability = Exclude<keyof IWorldCapabilities, 'readOnly'>

/** Tipo di un descrittore di campo (`FieldDescriptor.type`). */
export type FieldKind = 'int' | 'string' | 'text' | 'bool' | 'enum' | 'flags' | 'list' | 'dict' | 'number'

/** Descrittore di un campo di una risorsa (`FieldDescriptor`). */
export interface IFieldDescriptor {
  name: string
  type: FieldKind
  required: boolean
  readOnly: boolean
  /** Chiave in `GET /api/meta/enums` da cui prendere le opzioni (enum/flags). */
  enum: string | null
  nullable: boolean
  /** Il mondo non ha il campo: in lettura è neutro, in scrittura accetta solo il valore neutro. */
  unsupported?: boolean
}

/** Editor di una chiave di `extra` (`ExtraFieldDescriptor`). `flags` = lista di nomi, `enum` = nome dell'opzione, `select` = valore. */
export type ExtraKind = 'text' | 'number' | 'boolean' | 'flags' | 'enum' | 'select' | 'json'

/** Una chiave di `extra` dichiarata dal mondo per una risorsa (`describe()`). */
export interface IExtraFieldDescriptor {
  /** Chiave in `extra`. */
  name: string
  /** Chiave i18n dell'etichetta (`extra.labels.<name>`); se manca la traduzione si mostra il nome. */
  labelKey: string
  type: ExtraKind
  /** Chiave in `GET /api/meta/enums` con le opzioni (flags/enum/select). */
  enum: string | null
  readOnly: boolean
  /** Il testo vuoto vale `null`. */
  nullable: boolean
  /** Sezione del form; `diagnostic` = avvisi dell'adapter (mai nel form, mostrati come banner). */
  group: string | null
}

/** Risorsa di un mondo con i suoi campi. */
export interface IWorldResource {
  type: string
  fields: IFieldDescriptor[]
  /** Le chiavi di `extra` che il mondo emette per la risorsa. */
  extraFields: IExtraFieldDescriptor[]
  /** Zone: una zona nuova si aggiunge solo in coda (range di partenza derivato). */
  createAtEnd: boolean
}

/** Mondo come restituito da `GET /api/worlds`. */
export interface IWorld {
  id: string
  kind: string
  name: string
  default: boolean
  capabilities: IWorldCapabilities
  resources: IWorldResource[]
}
