import { markRaw } from 'vue'
import type { IFieldRow } from '@ilpachi/pachi-kit/fields'
import FlagsField from '../../shared/components/FlagsField.vue'
import type { IAccount, IPlayerLookups } from '../types/players'

/** Funzione di traduzione (`t` di vue-i18n). */
export type Translate = (key: string, params?: Record<string, unknown>) => string

/** Stile dei campi affiancati. */
const SIDE_BY_SIDE = 'flex: 1 1 0; min-width: 130px'

/**
 * Campo numerico affiancato.
 *
 * @param t - traduzione
 * @param field - nome del campo
 */
function num(t: Translate, field: string): { field: string; label: string; type: 'number'; style: string } {
  return { field, label: t(`players.fields.${field}`), type: 'number', style: SIDE_BY_SIDE }
}

/**
 * Righe della sezione "Identità" del personaggio.
 *
 * @param t - traduzione
 * @param lookups - sesso, razze, classi
 * @param accounts - account assegnabili
 */
export function buildIdentityRows(t: Translate, lookups: IPlayerLookups, accounts: IAccount[]): IFieldRow[] {
  return [
    [
      { field: 'name', label: t('players.fields.name'), required: true },
      { field: 'title', label: t('players.fields.title') },
    ],
    [
      {
        field: 'accountId',
        label: t('players.fields.accountId'),
        type: 'select',
        options: accounts,
        optionLabel: 'username',
        optionValue: 'id',
        style: SIDE_BY_SIDE,
      },
      { field: 'sex', label: t('players.fields.sex'), type: 'select', options: lookups.sex, style: SIDE_BY_SIDE },
    ],
    [
      {
        field: 'classId',
        label: t('players.fields.classId'),
        type: 'select',
        options: lookups.classes,
        optionLabel: 'name',
        optionValue: 'id',
        style: SIDE_BY_SIDE,
      },
      {
        field: 'raceId',
        label: t('players.fields.raceId'),
        type: 'select',
        options: lookups.races,
        optionLabel: 'name',
        optionValue: 'id',
        style: SIDE_BY_SIDE,
      },
    ],
    [num(t, 'level'), num(t, 'experience'), num(t, 'practices')],
  ]
}

/**
 * Righe della sezione "Stato" (punti, oro, posizione, condizioni).
 *
 * @param t - traduzione
 * @param lookups - posizioni
 */
export function buildStateRows(t: Translate, lookups: IPlayerLookups): IFieldRow[] {
  return [
    [num(t, 'hitPointsCurrent'), num(t, 'hitPointsMax')],
    [num(t, 'manaCurrent'), num(t, 'manaMax')],
    [num(t, 'gold'), num(t, 'bankGold'), num(t, 'questPoints')],
    [
      {
        field: 'position',
        label: t('players.fields.position'),
        type: 'select',
        options: lookups.position,
        style: SIDE_BY_SIDE,
      },
      num(t, 'alignment'),
      num(t, 'wimpyLevel'),
    ],
    [num(t, 'hunger'), num(t, 'thirst'), num(t, 'drunk'), num(t, 'poisonTicks')],
    [{ field: 'isPlayerKiller', label: t('players.fields.isPlayerKiller'), type: 'boolean' }],
  ]
}

/**
 * Righe della sezione "Caratteristiche".
 *
 * @param t - traduzione
 */
export function buildStatsRows(t: Translate): IFieldRow[] {
  return [
    [num(t, 'strength'), num(t, 'strengthPercentile'), num(t, 'dexterity')],
    [num(t, 'constitution'), num(t, 'intelligence'), num(t, 'wisdom'), num(t, 'charisma')],
  ]
}

/**
 * Righe della sezione "Liste" (abilità, preferenze, quest).
 *
 * @param t - traduzione
 */
export function buildListRows(t: Translate): IFieldRow[] {
  return ['knownSkillIds', 'preferences', 'activeQuestIds', 'completedQuestIds'].map((field) => [
    { field, label: t(`players.fields.${field}`), component: markRaw(FlagsField), hint: t('players.fields.listHint') },
  ])
}
