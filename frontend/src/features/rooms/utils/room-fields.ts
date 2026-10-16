import type { IFieldRow } from '@ilpachi/pachi-kit/fields'
import { flagsFieldDef } from '../../shared/helpers/descriptor-rows'
import type { IEnumOption } from '../types/rooms'

/** Funzione di traduzione minima (vue-i18n). */
type Translate = (key: string) => string

/**
 * Campi della sezione "generale" della stanza (vnum, terreno, nome, descrizione, recuperi, flag).
 *
 * @param t - traduzione
 * @param sectorOptions - opzioni del terreno (da `/api/meta/enums`)
 * @param vnumLocked - vero in modifica: il vnum non si cambia
 * @param flagNames - nomi noti dei flag del mondo (vuoto: elenco libero)
 */
export function buildRoomFieldRows(
  t: Translate,
  sectorOptions: IEnumOption[],
  vnumLocked: boolean,
  flagNames: string[] = [],
): IFieldRow[] {
  const intRule = (label: string) => (value: unknown) =>
    (typeof value === 'number' && Number.isInteger(value)) || `${label}: ${t('rooms.validation.integer')}`
  return [
    [
      {
        field: 'vnum',
        label: t('rooms.fields.vnum'),
        type: 'number',
        required: true,
        disable: vnumLocked,
        rules: [intRule(t('rooms.fields.vnum'))],
      },
      {
        field: 'sectorType',
        label: t('rooms.fields.sectorType'),
        type: 'select',
        options: sectorOptions,
        required: true,
      },
    ],
    [{ field: 'name', label: t('rooms.fields.name'), required: true }],
    [{ field: 'description', label: t('rooms.fields.description'), type: 'textarea', autogrow: true }],
    [
      { field: 'healRate', label: t('rooms.fields.healRate'), type: 'number' },
      { field: 'manaRate', label: t('rooms.fields.manaRate'), type: 'number' },
    ],
    [flagsFieldDef({ field: 'flags', label: t('rooms.fields.flags'), hint: t('rooms.fields.flagsHint') }, flagNames)],
  ]
}

/**
 * Campi del dialog di clonazione (nuovo vnum e nome opzionale).
 *
 * @param t - traduzione
 */
export function buildCloneFieldRows(t: Translate): IFieldRow[] {
  return [
    [{ field: 'vnum', label: t('rooms.clone.vnum'), type: 'number', required: true }],
    [{ field: 'name', label: t('rooms.clone.name'), hint: t('rooms.clone.hint') }],
  ]
}
