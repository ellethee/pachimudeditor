import { markRaw } from 'vue'
import type { IFieldRow } from '@ilpachi/pachi-kit/fields'
import { flagsFieldDef } from '../../shared/helpers/descriptor-rows'
import AffectsField from '../components/AffectsField.vue'
import VnumField from '../components/VnumField.vue'
import type { IObjectEnums } from '../types/objects'

/** Funzione di traduzione (`t` di vue-i18n). */
export type Translate = (key: string, params?: Record<string, unknown>) => string

/** Stile dei campi affiancati: dividono la riga in parti uguali (con minimo prima di andare a capo). */
const SIDE_BY_SIDE = 'flex: 1 1 0; min-width: 130px'

/**
 * Righe del form oggetto (sezione generale).
 *
 * @param t - traduzione
 * @param enums - enum del backend (tipo oggetto)
 * @param zoneId - zona in cui si crea/modifica (per il suggerimento del vnum)
 * @param editing - `true` in modifica (il vnum non è modificabile)
 */
export function buildGeneralRows(
  t: Translate,
  enums: IObjectEnums | undefined,
  zoneId: number,
  editing: boolean,
): IFieldRow[] {
  return [
    [
      {
        field: 'vnum',
        label: t('objects.fields.vnum'),
        component: markRaw(VnumField),
        required: true,
        zoneId,
        disable: editing,
      },
      { field: 'objectType', label: t('objects.fields.objectType'), type: 'select', options: enums?.objectType ?? [], style: SIDE_BY_SIDE },
    ],
    [{ field: 'keywords', label: t('objects.fields.keywords'), required: true }],
    [{ field: 'shortDescription', label: t('objects.fields.shortDescription'), required: true }],
    [{ field: 'longDescription', label: t('objects.fields.longDescription') }],
    [{ field: 'actionDescription', label: t('objects.fields.actionDescription') }],
  ]
}

/**
 * Righe della sezione "Statistiche e flag" del form oggetto.
 *
 * @param t - traduzione
 * @param enums - enum del backend (bersagli degli affects, se esposti)
 * @param extraFlagNames - nomi noti dei flag extra del mondo (vuoto: elenco libero)
 * @param wearFlagNames - nomi noti dei flag di indossabilità del mondo (vuoto: elenco libero)
 */
export function buildStatsRows(
  t: Translate,
  enums?: IObjectEnums,
  extraFlagNames: string[] = [],
  wearFlagNames: string[] = [],
): IFieldRow[] {
  const num = (
    field: string,
    hint?: string,
  ): { field: string; label: string; type: 'number'; style: string; hint?: string } => ({
    field,
    label: t(`objects.fields.${field}`),
    type: 'number',
    style: SIDE_BY_SIDE,
    ...(hint ? { hint } : {}),
  })
  return [
    [num('weight'), num('cost'), num('rent')],
    [num('value0', t('objects.fields.valueHint')), num('value1'), num('value2'), num('value3')],
    [
      flagsFieldDef(
        { field: 'extraFlags', label: t('objects.fields.extraFlags'), hint: t('objects.fields.extraFlagsHint') },
        extraFlagNames,
      ),
    ],
    [
      flagsFieldDef(
        { field: 'wearFlags', label: t('objects.fields.wearFlags'), hint: t('objects.fields.wearFlagsHint') },
        wearFlagNames,
      ),
    ],
      [
      {
        field: 'affects',
        label: t('objects.fields.affects'),
        component: markRaw(AffectsField),
        hint: enums?.buffTarget?.length ? t('objects.fields.affectsHint') : t('objects.fields.affectsFreeHint'),
        targetOptions: enums?.buffTarget ?? [],
      },
    ],
  ]
}
