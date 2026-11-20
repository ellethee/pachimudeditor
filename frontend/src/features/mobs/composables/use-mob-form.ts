import { markRaw } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ISectionDefinition } from '@ilpachi/pachi-kit/edit-dialog'
import { FieldsSection } from '@ilpachi/pachi-kit/fields'
import type { IFieldRow } from '@ilpachi/pachi-kit/fields'
import InstancesSection from '../../instances/components/InstancesSection.vue'
import { applyDescriptors, enumNames } from '../../shared/helpers/descriptor-rows'
import { localizeEnums } from '../../shared/helpers/enum-labels'
import { createExtraEditor } from '../../shared/helpers/extra-fields'
import { guardOf, guardSection } from '../../shared/helpers/record-guard'
import { useWorld } from '../../shared/helpers/world-state'
import ShopField from '../../shops/components/ShopField.vue'
import { normalizeShop, shopProblems } from '../../shops/helpers/shop-defaults'
import { buildCombatRows, buildIdentityRows, buildRoleRows } from '../helpers/field-rows'
import { getEnums, listClasses, listRaces, nextMobVnum } from '../services/mobs-api'
import type { IContentRef, IMobEnums, IMobs, IMobsInput } from '../types/mobs'

/** Tabelle di supporto del form mob (enum, razze, classi). */
export interface IMobLookups {
  enums: IMobEnums
  races: IContentRef[]
  classes: IContentRef[]
}

/** Carica enum (localizzati), razze e classi. */
export async function loadMobLookups(): Promise<IMobLookups> {
  const [enums, races, classes] = await Promise.all([getEnums(), listRaces(), listClasses()])
  return { enums: localizeEnums(enums), races, classes }
}

/**
 * Valori iniziali del form per un nuovo mob.
 *
 * @param zoneId - zona di destinazione
 * @param enums - enum del backend
 */
function emptyMob(zoneId: number, enums: IMobEnums): IMobsInput {
  return {
    vnum: 0,
    zoneId,
    keywords: '',
    shortDescription: '',
    longDescription: '',
    detailedDescription: '',
    level: 1,
    thac0: 20,
    armorClass: 0,
    hpDiceCount: 1,
    hpDieSize: 8,
    hpBonus: 0,
    damageDiceCount: 1,
    damageDieSize: 4,
    damageBonus: 0,
    gold: 0,
    experience: 0,
    sex: enums.sex[0]?.value ?? 0,
    flags: [],
    raceId: null,
    classId: null,
    alignment: 0,
    debuffSkillId: null,
    shopId: null,
    questIds: [],
    isBanker: false,
    teachesClassIds: null,
    teachesSkillIds: null,
  }
}

/**
 * Form di un mob (sezioni, blocco in sola lettura, raccolta dei dati): lo usano il dialogo di creazione e la pagina
 * di dettaglio. Da chiamare in `setup()`.
 */
export function useMobForm() {
  const { t, te } = useI18n()
  const { readOnly, supports, fieldOf, extraFieldsOf, declaresExtra } = useWorld()

  /**
   * Prepara il form.
   *
   * @param lookups - tabelle di supporto
   * @param record - mob da modificare; assente per la creazione
   * @param createZoneId - zona del nuovo mob (solo creazione)
   */
  async function prepareMobForm(lookups: IMobLookups, record?: IMobs, createZoneId?: number) {
    const zoneId = (record?.zoneId ?? createZoneId) as number
    const enumsRaw = lookups.enums as unknown as Record<string, unknown>
    const initial: Record<string, unknown> = record ? { ...record } : { ...emptyMob(zoneId, lookups.enums) }
    // le liste opzionali nulle si mostrano come vuote (chip/select multiplo)
    initial.questIds = initial.questIds ?? []
    initial.teachesClassIds = initial.teachesClassIds ?? []
    initial.teachesSkillIds = initial.teachesSkillIds ?? []
    if (!record) {
      // creazione: propone subito il prossimo vnum libero della zona (l'utente può cambiarlo)
      try {
        initial.vnum = await nextMobVnum(zoneId)
      } catch {
        // resta 0: il pulsante del campo vnum permette di riprovare
      }
    }
    const guard = guardOf(record?.extra)
    const locked = readOnly.value || guard.corrupted
    const lockRows = (rows: IFieldRow[]): IFieldRow[] =>
      guard.corrupted ? rows.map((row) => row.map((def) => ({ ...def, disable: true, readonly: true }))) : rows
    const rowsOf = (rows: IFieldRow[]): IFieldRow[] => lockRows(applyDescriptors(rows, 'mob', fieldOf, t))
    // il mondo dichiara `extra.shop` (pachimud): il negozio ha una scheda propria, non il JSON grezzo fra gli altri campi
    const hasShop = extraFieldsOf('mob').some((desc) => desc.name === 'shop')
    const extraEditor = createExtraEditor({
      exclude: hasShop ? ['shop'] : [],
      t,
      te,
      descriptors: extraFieldsOf('mob'),
      declared: declaresExtra('mob'),
      readonly: locked,
      extra: record?.extra,
      enums: enumsRaw,
      order: 40,
    })
    const sections: ISectionDefinition[] = [
      {
        key: 'identity',
        title: t('mobs.sections.identity'),
        component: markRaw(FieldsSection),
        props: { rows: rowsOf(buildIdentityRows(t, zoneId, !!record)) },
        initialValue: initial,
        order: 10,
        container: { type: 'card', flat: true, bordered: true, class: 'q-pa-md q-mb-md' },
      },
      {
        key: 'combat',
        title: t('mobs.sections.combat'),
        component: markRaw(FieldsSection),
        props: {
          rows: rowsOf(
            buildCombatRows(t, lookups.enums, lookups.races, lookups.classes, enumNames(enumsRaw, fieldOf('mob', 'flags'))),
          ),
        },
        initialValue: initial,
        order: 20,
        container: { type: 'expansion', title: t('mobs.sections.combat'), defaultOpened: true },
      },
      {
        key: 'roles',
        title: t('mobs.sections.roles'),
        component: markRaw(FieldsSection),
        props: { rows: rowsOf(buildRoleRows(t, lookups.classes)) },
        initialValue: initial,
        order: 30,
        container: { type: 'expansion', title: t('mobs.sections.roles'), defaultOpened: false },
      },
    ]
    if (hasShop) {
      const shop = record?.extra?.shop ?? null
      sections.push({
        key: 'shop',
        title: t('shops.sectionTitle'),
        component: markRaw(FieldsSection),
        props: {
          rows: [
            [
              {
                field: 'shop',
                label: t('shops.sectionTitle'),
                component: markRaw(ShopField),
                readonly: locked,
                legacyShopId: record?.shopId ?? null,
                // non si salva un negozio non valido (la scheda mostra il perché)
                rules: [(value: unknown) => ((normalizeShop(value) && shopProblems(normalizeShop(value)!).length > 0) ? t('shops.errors.invalid') : true)],
              },
            ],
          ],
        },
        initialValue: { shop },
        order: 35,
        container: { type: 'expansion', title: t('shops.sectionTitle'), defaultOpened: shop !== null },
      })
    }
    if (extraEditor) sections.push(extraEditor.section)
    const banner = guardSection(guard)
    if (banner) sections.unshift(banner)
    if (record && supports('supportsInstances') && !guard.corrupted) {
      sections.push({
        key: 'instances',
        title: t('worlds.instances'),
        component: markRaw(InstancesSection),
        props: { kind: 'mob', prototypeId: record.id },
        initialValue: {},
        order: 50,
        container: { type: 'expansion', title: t('worlds.instances'), defaultOpened: false },
      })
    }

    /**
     * Unisce i risultati delle sezioni nel corpo da inviare.
     * @param results `data.sections` del dialogo / `getResults()` del form
     */
    function collect(results: Record<string, unknown>): Partial<IMobsInput> {
      const body = {
        ...(results.identity as Record<string, unknown>),
        ...(results.combat as Record<string, unknown>),
        ...(results.roles as Record<string, unknown>),
      } as Partial<IMobsInput>
      // campi opzionali: stringa vuota -> null; liste di insegnamento vuote -> null
      if (!body.shopId) body.shopId = null
      if (!body.debuffSkillId) body.debuffSkillId = null
      if (!body.teachesClassIds?.length) body.teachesClassIds = null
      if (!body.teachesSkillIds?.length) body.teachesSkillIds = null
      // `extra` (campi specifici del mondo) solo con le chiavi cambiate
      const extra = extraEditor?.collect(results.extra)
      if (extra) body.extra = extra
      if (hasShop) {
        // `null` toglie il negozio; confrontato con quello salvato per non toccare il file se non è cambiato
        const next = (results.shop as { shop?: unknown } | undefined)?.shop ?? null
        if (JSON.stringify(next) !== JSON.stringify(record?.extra?.shop ?? null)) body.extra = { ...body.extra, shop: next }
      }
      return body
    }

    return { sections, locked, guard, initial, zoneId, collect }
  }

  return { prepareMobForm }
}
