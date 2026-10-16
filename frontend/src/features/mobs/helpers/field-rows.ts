import { markRaw } from 'vue'
import type { IFieldRow } from '@ilpachi/pachi-kit/fields'
import FlagsField from '../../shared/components/FlagsField.vue'
import { flagsFieldDef } from '../../shared/helpers/descriptor-rows'
import VnumField from '../components/VnumField.vue'
import type { IContentRef, IMobEnums } from '../types/mobs'

/** Funzione di traduzione (`t` di vue-i18n). */
export type Translate = (key: string, params?: Record<string, unknown>) => string

/** Stile dei campi affiancati: dividono la riga in parti uguali (con minimo prima di andare a capo). */
const SIDE_BY_SIDE = 'flex: 1 1 0; min-width: 130px'

/**
 * Righe della sezione "Identità" del form mob.
 *
 * @param t - traduzione
 * @param zoneId - zona in cui si crea/modifica (per il suggerimento del vnum)
 * @param editing - `true` in modifica (il vnum non è modificabile)
 */
export function buildIdentityRows(t: Translate, zoneId: number, editing: boolean): IFieldRow[] {
  return [
    [
      {
        field: 'vnum',
        label: t('mobs.fields.vnum'),
        component: markRaw(VnumField),
        required: true,
        zoneId,
        disable: editing,
      },
      { field: 'keywords', label: t('mobs.fields.keywords'), required: true },
    ],
    [{ field: 'shortDescription', label: t('mobs.fields.shortDescription'), required: true }],
    [{ field: 'longDescription', label: t('mobs.fields.longDescription') }],
    [
      {
        field: 'detailedDescription',
        label: t('mobs.fields.detailedDescription'),
        type: 'textarea',
        autogrow: true,
      },
    ],
  ]
}

/**
 * Righe della sezione "Combattimento e attributi" del form mob.
 *
 * @param t - traduzione
 * @param enums - enum del backend (sesso)
 * @param races - razze disponibili
 * @param classes - classi disponibili
 * @param flagNames - nomi noti dei flag del mondo (vuoto: elenco libero)
 */
export function buildCombatRows(
  t: Translate,
  enums: IMobEnums | undefined,
  races: IContentRef[],
  classes: IContentRef[],
  flagNames: string[] = [],
): IFieldRow[] {
  const num = (field: string): { field: string; label: string; type: 'number'; style: string } => ({
    field,
    label: t(`mobs.fields.${field}`),
    type: 'number',
    style: SIDE_BY_SIDE,
  })
  return [
    [num('level'), num('thac0'), num('armorClass')],
    [num('hpDiceCount'), num('hpDieSize'), num('hpBonus')],
    [num('damageDiceCount'), num('damageDieSize'), num('damageBonus')],
    [
      num('gold'),
      num('experience'),
      {
        ...num('alignment'),
        rules: [
          (v: unknown) =>
            v === null || (Number(v) >= -1000 && Number(v) <= 1000) || t('mobs.validation.alignmentRange'),
        ],
      },
    ],
    [
      { field: 'sex', label: t('mobs.fields.sex'), type: 'select', options: enums?.sex ?? [], style: SIDE_BY_SIDE },
      {
        field: 'raceId',
        label: t('mobs.fields.raceId'),
        type: 'select',
        options: races,
        optionLabel: 'name',
        optionValue: 'id',
        clearable: true,
        style: SIDE_BY_SIDE,
      },
      {
        field: 'classId',
        label: t('mobs.fields.classId'),
        type: 'select',
        options: classes,
        optionLabel: 'name',
        optionValue: 'id',
        clearable: true,
        style: SIDE_BY_SIDE,
      },
    ],
    [flagsFieldDef({ field: 'flags', label: t('mobs.fields.flags'), hint: t('mobs.fields.flagsHint') }, flagNames)],
  ]
}

/**
 * Righe della sezione "Ruoli e servizi" del form mob (banchiere, negozio, quest, insegnamento, debuff).
 *
 * @param t - traduzione
 * @param classes - classi disponibili (per `teachesClassIds`)
 */
export function buildRoleRows(t: Translate, classes: IContentRef[]): IFieldRow[] {
  const chips = (field: string): IFieldRow[number] => ({
    field,
    label: t(`mobs.fields.${field}`),
    component: markRaw(FlagsField),
    hint: t(`mobs.fields.${field}Hint`),
  })
  return [
    [
      { field: 'isBanker', label: t('mobs.fields.isBanker'), type: 'boolean', style: SIDE_BY_SIDE },
      { field: 'shopId', label: t('mobs.fields.shopId'), hint: t('mobs.fields.shopIdHint'), style: SIDE_BY_SIDE },
      {
        field: 'debuffSkillId',
        label: t('mobs.fields.debuffSkillId'),
        hint: t('mobs.fields.debuffSkillIdHint'),
        style: SIDE_BY_SIDE,
      },
    ],
    [chips('questIds')],
    [
      {
        field: 'teachesClassIds',
        label: t('mobs.fields.teachesClassIds'),
        type: 'select',
        options: classes,
        optionLabel: 'name',
        optionValue: 'id',
        multiple: true,
        useChips: true,
        clearable: true,
      },
    ],
    [chips('teachesSkillIds')],
  ]
}
