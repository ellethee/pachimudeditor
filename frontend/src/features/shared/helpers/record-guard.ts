import { markRaw } from 'vue'
import type { ISectionDefinition } from '@ilpachi/pachi-kit/edit-dialog'
import RecordBannerSection from '../components/RecordBannerSection.vue'

/** Stato di integrità di un record, letto da `extra` (chiavi di diagnostica dichiarate dall'adapter). */
export interface IRecordGuard {
  /** Record illeggibile nel file originale: solo lettura, né salvataggio né eliminazione. */
  corrupted: boolean
  /** Motivo o avviso dell'adapter (`extra.warning`), se presente. */
  warning: string | null
}

/**
 * Stato di integrità di un record.
 *
 * @param extra - `extra` del record (anche assente)
 */
export function guardOf(extra: Record<string, unknown> | undefined): IRecordGuard {
  const warning = extra?.warning
  return { corrupted: extra?.corrupted === true, warning: typeof warning === 'string' && warning ? warning : null }
}

/**
 * Sezione-banner da mettere in testa al dialog (`null` se il record è integro e senza avvisi).
 *
 * @param guard - esito di {@link guardOf}
 */
export function guardSection(guard: IRecordGuard): ISectionDefinition | null {
  if (!guard.corrupted && guard.warning === null) return null
  return {
    key: 'guard',
    title: '',
    component: markRaw(RecordBannerSection),
    props: { corrupted: guard.corrupted, message: guard.warning ?? '' },
    initialValue: {},
    order: 0,
  }
}

/** Classe CSS del dialog di un record bloccato: nasconde il pulsante di salvataggio (vedi `app.scss`). */
export const LOCKED_DIALOG_CLASS = 'pachi-record-locked'
