import { markRaw } from 'vue'
import type { IFieldRow } from '@ilpachi/pachi-kit/fields'
import YamlField from '../../shared/components/YamlField.vue'
import type { Translate } from './field-rows'
import type { ISkill, ISocial } from '../types/content-files'

/** Stile dei campi affiancati: dividono la riga in parti uguali. */
const SIDE = 'flex: 1 1 0; min-width: 130px'
/** Tipi, tiri salvezza ed elementi ammessi dal gioco (`docs/contenuti.md`). */
const KINDS = ['spell', 'skill']
const SAVINGS = ['para', 'rod', 'petri', 'breath', 'spell']
/** Oggetti in cui può stare un incantesimo (`item_types`). */
export const ITEM_TYPES = ['potion', 'scroll', 'wand', 'staff', 'ointment']
const ELEMENTS = ['fire', 'elec', 'cold', 'energy', 'acid', 'poison', 'blunt', 'pierce', 'slash']
/** Chiavi dei testi di un social. */
export const SOCIAL_KEYS = ['no_arg', 'others_no_arg', 'found', 'others_found', 'victim_found', 'not_found', 'auto', 'others_auto'] as const
/** Lingue sempre proposte per i testi di un social. */
export const SOCIAL_LANGS = ['it', 'en']

/** Opzioni `{ value, label }` da un elenco di stringhe. */
function options(values: string[]): { value: string; label: string }[] {
  return values.map((value) => ({ value, label: value }))
}

/** Regola: id ammesso (minuscole, cifre, underscore). */
function idRule(message: string) {
  return (value: unknown) => /^[a-z0-9][a-z0-9_]{0,63}$/.test(String(value ?? '')) || message
}

/**
 * Righe del form di una skill: campi semplici; `advanced` (YAML) per effetti, livelli, testi e il resto.
 * @param t traduzione
 * @param editing `true` in modifica (l'id non è modificabile)
 */
export function buildSkillRows(t: Translate, editing: boolean): { general: IFieldRow[]; advanced: IFieldRow[] } {
  return {
    general: [
      [
        { field: 'skillId', label: t('content.skills.fields.skillId'), required: true, disable: editing, rules: [idRule(t('content.validation.id'))], style: SIDE },
        { field: 'name', label: t('content.skills.fields.name'), required: true, style: SIDE },
        { field: 'kind', label: t('content.skills.fields.kind'), type: 'select', options: options(KINDS), clearable: true, style: SIDE },
      ],
      [{ field: 'description', label: t('content.skills.fields.description'), type: 'textarea', autogrow: true }],
      [
        { field: 'mana', label: t('content.skills.fields.mana'), type: 'number', style: SIDE },
        { field: 'beats', label: t('content.skills.fields.beats'), type: 'number', style: SIDE },
        { field: 'fail', label: t('content.skills.fields.fail'), type: 'number', style: SIDE },
        { field: 'maxLearn', label: t('content.skills.fields.maxLearn'), type: 'number', style: SIDE },
      ],
      [
        { field: 'minPosition', label: t('content.skills.fields.minPosition'), hint: t('content.skills.fields.minPositionHint'), style: SIDE },
        { field: 'saving', label: t('content.skills.fields.saving'), type: 'select', options: options(SAVINGS), clearable: true, style: SIDE },
        { field: 'element', label: t('content.skills.fields.element'), type: 'select', options: options(ELEMENTS), clearable: true, style: SIDE },
      ],
      [{ field: 'targets', label: t('content.skills.fields.targets'), hint: t('content.skills.fields.targetsHint') }],
      [
        {
          field: 'itemTypes',
          label: t('content.skills.fields.itemTypes'),
          hint: t('content.skills.fields.itemTypesHint'),
          type: 'select',
          multiple: true,
          useChips: true,
          clearable: true,
          options: ITEM_TYPES.map((value) => ({ value, label: t(`content.skills.itemTypes.${value}`) })),
        },
      ],
      [
        { field: 'violent', label: t('content.skills.fields.violent'), type: 'boolean' },
        { field: 'disabled', label: t('content.skills.fields.disabled'), type: 'boolean' },
      ],
    ],
    advanced: [
      [
        {
          field: 'advanced',
          label: t('content.skills.fields.advanced'),
          hint: t('content.skills.fields.advancedHint'),
          component: markRaw(YamlField),
        },
      ],
    ],
  }
}

/**
 * Dal form al corpo della richiesta: booleani falsi e campi vuoti tolgono la chiave dal file; `targets` è una lista.
 * @param values valori delle sezioni unite
 * @param editing `true` in modifica (senza `skillId`: sta nel percorso)
 * @param original la skill com'era (`item_types` si invia solo se è cambiato: assente e lista vuota non sono la stessa cosa)
 */
export function formToSkill(values: Record<string, unknown>, editing: boolean, original: ISkill | null = null): Record<string, unknown> {
  const text = (v: unknown): string | null => (typeof v === 'string' && v.trim() !== '' ? v.trim() : null)
  const num = (v: unknown): number | null => (v === null || v === undefined || v === '' ? null : Number(v))
  const body: Record<string, unknown> = {
    kind: text(values.kind),
    name: text(values.name),
    description: text(values.description),
    mana: num(values.mana),
    beats: num(values.beats),
    fail: num(values.fail),
    maxLearn: num(values.maxLearn),
    minPosition: text(values.minPosition),
    saving: text(values.saving),
    element: text(values.element),
    targets: String(values.targets ?? '')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
    violent: values.violent === true ? true : null,
    disabled: values.disabled === true ? true : null,
    advanced: String(values.advanced ?? ''),
  }
  if ((body.targets as string[]).length === 0) body.targets = null
  const types = Array.isArray(values.itemTypes) ? (values.itemTypes as string[]) : []
  const before = original?.itemTypes ?? undefined // l'API manda `null` se la chiave manca
  const same = before !== undefined && before.length === types.length && before.every((x) => types.includes(x))
  if (original && (same || (before === undefined && types.length === 0))) delete body.itemTypes
  else body.itemTypes = types.length > 0 ? types : null
  if (!editing) body.skillId = String(values.skillId ?? '').trim()
  return body
}

/**
 * Dalla skill al form.
 * @param skill skill letta dal backend (`null` = nuova)
 */
export function skillToForm(skill: ISkill | null): Record<string, unknown> {
  return {
    skillId: skill?.skillId ?? '',
    name: skill?.name ?? '',
    kind: skill?.kind ?? 'spell',
    description: skill?.description ?? '',
    mana: skill?.mana ?? null,
    beats: skill?.beats ?? null,
    fail: skill?.fail ?? null,
    maxLearn: skill?.maxLearn ?? null,
    minPosition: skill?.minPosition ?? '',
    saving: skill?.saving ?? null,
    element: skill?.element ?? null,
    targets: (skill?.targets ?? []).join(', '),
    itemTypes: skill?.itemTypes ?? [],
    violent: skill?.violent ?? false,
    disabled: skill?.disabled ?? false,
    advanced: skill?.advanced ?? '',
  }
}

/**
 * Righe del form di un social: dati generali e, per lingua, gli otto testi.
 * @param t traduzione
 * @param editing `true` in modifica (il nome non è modificabile)
 * @param langs lingue da mostrare
 */
export function buildSocialRows(t: Translate, editing: boolean, langs: string[]): { general: IFieldRow[]; langs: Record<string, IFieldRow[]> } {
  const byLang: Record<string, IFieldRow[]> = {}
  for (const lang of langs) {
    byLang[lang] = SOCIAL_KEYS.map((key) => [
      { field: `${lang}_${key}`, label: t(`content.socials.keys.${key}`), type: 'textarea', autogrow: true, rows: 1 },
    ])
  }
  return {
    general: [
      [
        { field: 'name', label: t('content.socials.fields.name'), required: true, disable: editing, rules: [idRule(t('content.validation.id'))], style: SIDE },
        { field: 'aliases', label: t('content.socials.fields.aliases'), hint: t('content.socials.fields.aliasesHint'), style: SIDE },
        { field: 'position', label: t('content.socials.fields.position'), hint: t('content.socials.fields.positionHint'), style: SIDE },
        { field: 'victimMinPosition', label: t('content.socials.fields.victimMinPosition'), type: 'number', style: SIDE },
      ],
      [{ field: 'hide', label: t('content.socials.fields.hide'), type: 'boolean' }],
    ],
    langs: byLang,
  }
}

/**
 * Dal social al form (i testi diventano campi `<lingua>.<chiave>`).
 * @param social social letto dal backend (`null` = nuovo)
 * @param langs lingue mostrate
 */
export function socialToForm(social: ISocial | null, langs: string[]): Record<string, unknown> {
  const form: Record<string, unknown> = {
    name: social?.name ?? '',
    aliases: (social?.aliases ?? []).join(', '),
    position: social?.position ?? 'resting',
    victimMinPosition: social?.victimMinPosition ?? 0,
    hide: social?.hide ?? false,
  }
  for (const lang of langs) for (const key of SOCIAL_KEYS) form[`${lang}_${key}`] = social?.messages[lang]?.[key] ?? ''
  return form
}

/**
 * Dal form al corpo della richiesta (testi vuoti omessi dal backend).
 * @param values valori delle sezioni unite
 * @param langs lingue mostrate
 */
export function formToSocial(values: Record<string, unknown>, langs: string[]): Record<string, unknown> {
  const messages: Record<string, Record<string, string>> = {}
  for (const lang of langs) {
    messages[lang] = Object.fromEntries(SOCIAL_KEYS.map((key) => [key, String(values[`${lang}_${key}`] ?? '')]))
  }
  return {
    aliases: String(values.aliases ?? '')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
    position: String(values.position ?? '').trim() || 'resting',
    victimMinPosition: Number(values.victimMinPosition ?? 0),
    hide: values.hide === true,
    messages,
  }
}
