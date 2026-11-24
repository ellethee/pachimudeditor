import { markRaw } from 'vue'
import { FieldsSection } from '@ilpachi/pachi-kit/fields'
import type { ISectionDefinition } from '@ilpachi/pachi-kit/edit-dialog'
import TriggersField from '../components/TriggersField.vue'
import type { ITrigger, TriggerOwner } from '../types/triggers'
import { settledTriggers, triggerComplete } from './triggers'

/** Il campo di `extra` che contiene i trigger: gli oggetti usano `scripts` (in `triggers` le trappole hanno le direzioni). */
export function triggersField(owner: TriggerOwner): 'triggers' | 'scripts' {
  return owner === 'object' ? 'scripts' : 'triggers'
}

/**
 * La sezione «Trigger» (o «Script») di un form: lo stesso componente per mob, oggetti e stanze.
 * @param owner di chi sono i trigger
 * @param extra `extra` del record (`undefined` in creazione)
 * @param vnum vnum del record (per i problemi del controllo)
 * @param locked sola lettura
 * @param title titolo della sezione
 * @param invalid messaggio se un trigger non è completo
 * @param order posizione tra le sezioni
 */
export function buildTriggersSection(
  owner: TriggerOwner,
  extra: Record<string, unknown> | undefined,
  vnum: number | null,
  locked: boolean,
  title: string,
  invalid: string,
  order: number,
): ISectionDefinition {
  const field = triggersField(owner)
  const triggers = settledTriggers(extra?.[field])
  return {
    key: field,
    title,
    component: markRaw(FieldsSection),
    props: {
      rows: [
        [
          {
            field,
            label: title,
            component: markRaw(TriggersField),
            readonly: locked,
            owner,
            vnum,
            rules: [(value: unknown) => (settledTriggers(value).every(triggerComplete) ? true : invalid)],
          },
        ],
      ],
    },
    initialValue: { [field]: triggers },
    order,
    container: { type: 'expansion', title, defaultOpened: triggers.length > 0 },
  }
}

/**
 * I trigger da inviare: `undefined` se non sono cambiati (un salvataggio che non li tocca lascia il campo com'è nel file).
 * @param owner di chi sono i trigger
 * @param results `data.sections` del form
 * @param extra `extra` del record salvato
 */
export function collectTriggers(owner: TriggerOwner, results: Record<string, unknown>, extra: Record<string, unknown> | undefined): ITrigger[] | undefined {
  const field = triggersField(owner)
  const next = settledTriggers((results[field] as Record<string, unknown> | undefined)?.[field])
  return JSON.stringify(next) !== JSON.stringify(settledTriggers(extra?.[field])) ? next : undefined
}
