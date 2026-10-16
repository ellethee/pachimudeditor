/** Opzione `{ value, label }` di una select. */
export interface IOption {
  value: number
  label: string
}

/** Riferimento a contenuto YAML (razza/classe). */
export interface IContentRef {
  id: string
  name: string
}

/** Elenchi per i form (`GET /api/players/lookups`). */
export interface IPlayerLookups {
  sex: IOption[]
  position: IOption[]
  races: IContentRef[]
  classes: IContentRef[]
}

/** Account di gioco (mai con l'hash della password). */
export interface IAccount {
  id: number
  username: string
  email: string | null
  createdAt: string
  lastLoginAt: string | null
  isBanned: boolean
  characterCount: number
}

/** Corpo di creazione di un account. */
export interface IAccountInput {
  username: string
  password: string
  email: string | null
}

/** Riga di lista di un personaggio. */
export interface ICharacter {
  id: number
  accountId: number
  accountUsername: string | null
  name: string
  level: number
  classId: string
  raceId: string
  sex: number
  gold: number
  hitPointsCurrent: number
  hitPointsMax: number
  currentRoomId: number | null
  currentRoomVnum: number | null
  currentRoomName: string | null
  createdAt: string
  lastPlayedAt: string | null
}

/** Scheda completa di un personaggio. */
export interface ICharacterDetail extends ICharacter {
  experience: number
  manaCurrent: number
  manaMax: number
  strength: number
  strengthPercentile: number
  dexterity: number
  constitution: number
  intelligence: number
  wisdom: number
  charisma: number
  practices: number
  alignment: number
  position: number
  hunger: number
  thirst: number
  drunk: number
  poisonTicks: number
  wimpyLevel: number
  isPlayerKiller: boolean
  title: string
  questPoints: number
  bankGold: number
  knownSkillIds: string[]
  preferences: string[]
  activeQuestIds: string[]
  completedQuestIds: string[]
  skillPercentages: Record<string, number>
  questProgress: Record<string, number>
  itemCount: number
}

/** Patch parziale di un personaggio (solo i campi inviati). */
export type ICharacterPatch = Partial<
  Omit<
    ICharacterDetail,
    | 'id'
    | 'accountUsername'
    | 'currentRoomVnum'
    | 'currentRoomName'
    | 'createdAt'
    | 'lastPlayedAt'
    | 'skillPercentages'
    | 'questProgress'
    | 'itemCount'
  >
>

/** Oggetto nell'inventario di un personaggio. */
export interface IInventoryItem {
  id: number
  prototypeId: number
  vnum: number
  keywords: string
  shortDescription: string
  objectType: number
  equippedSlot: string | null
  containerInstanceId: number | null
  wearFlags: string[]
  liquidAmount: number | null
  charges: number | null
}

/** Risposta paginata generica. */
export interface IPage<T> {
  items: T[]
  total: number
  page?: number
  pageSize?: number
  pages?: number
}

/** Stanza (campi usati dal selettore di teletrasporto). */
export interface IRoomRef {
  id: number
  vnum: number
  name: string
}

/** Prototipo di oggetto (campi usati dal selettore dell'inventario). */
export interface IObjectRef {
  id: number
  vnum: number
  shortDescription: string
}
