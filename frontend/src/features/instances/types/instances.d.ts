/** Tipo di istanza gestita dalla feature. */
export type InstanceKind = 'mob' | 'object'

/** Dove può stare un oggetto vivo. */
export type LocationKind = 'room' | 'container' | 'mob' | 'character'

/** Cosa fare del contenuto eliminando un mob/contenitore. */
export type ContentsPolicy = 'destroy' | 'drop'

/** Opzione `{ value, label }` di una select remota. */
export interface IRemoteOption {
  value: number
  label: string
}

/** Zona (solo i campi usati dai selettori). */
export interface IZoneRef {
  id: number
  vnum: number
  name: string
}

/** Stanza (campi di `GET /api/rooms` usati dal selettore). */
export interface IRoomRef {
  id: number
  vnum: number
  name: string
  zoneId: number
}

/** Prototipo (mob o oggetto) di cui si elencano le istanze. */
export interface IPrototypeRef {
  id: number
  vnum: number
  zoneId: number
  shortDescription: string
  /** Solo oggetti: tipo (`ObjectType`). */
  objectType?: number
  /** Solo oggetti: slot di indossamento possibili (`wearFlags`). */
  wearFlags?: string[]
}

/** Mob vivo (`GET /api/instances/mobs`). */
export interface IMobInstance {
  id: number
  prototypeId: number
  prototypeVnum: number
  prototypeName: string
  prototypeZoneId: number
  shopId: string | null
  roomId: number
  roomVnum: number
  roomName: string
  zoneId: number
  zoneName: string
  hitPointsCurrent: number
  hitPointsMax: number
  gold: number | null
  itemCount: number
}

/** Oggetto vivo (`GET /api/instances/objects`). */
export interface IObjectInstance {
  id: number
  prototypeId: number
  prototypeVnum: number
  prototypeName: string
  prototypeZoneId: number
  objectType: number
  wearSlots: string[]
  locationKind: LocationKind
  locationId: number
  locationLabel: string
  equippedSlot: string | null
  roomId: number | null
  roomVnum: number | null
  roomName: string | null
  zoneId: number | null
  zoneName: string | null
  charges: number | null
  liquidAmount: number | null
  liquidType: number | null
  liquidPoisoned: boolean | null
  contentCount: number
}

/** Mob con gli oggetti che porta. */
export interface IMobInstanceDetail extends IMobInstance {
  items: IObjectInstance[]
}

/** Oggetto con il suo contenuto. */
export interface IObjectInstanceDetail extends IObjectInstance {
  contents: IObjectInstance[]
}

/** Posizione di un oggetto (corpo di creazione/spostamento). */
export interface ILocationInput {
  kind: LocationKind
  targetId: number
  equippedSlot?: string | null | undefined
}

/** Corpo di `POST /api/instances/mobs`. */
export interface IMobInstanceCreate {
  prototypeId: number
  roomId: number
  hitPoints?: number | null | undefined
  gold?: number | null | undefined
}

/** Corpo di `PUT /api/instances/mobs/{id}` (patch parziale). */
export interface IMobInstancePatch {
  hitPointsCurrent?: number | undefined
  hitPointsMax?: number | undefined
  gold?: number | null | undefined
  roomId?: number | undefined
}

/** Corpo di `POST /api/instances/objects`. */
export interface IObjectInstanceCreate {
  prototypeId: number
  location: ILocationInput
  charges?: number | null | undefined
  liquidAmount?: number | null | undefined
}

/** Corpo di `PUT /api/instances/objects/{id}` (patch parziale). */
export interface IObjectInstancePatch {
  charges?: number | null | undefined
  liquidAmount?: number | null | undefined
  liquidType?: number | null | undefined
  liquidPoisoned?: boolean | null | undefined
  location?: ILocationInput | undefined
}
