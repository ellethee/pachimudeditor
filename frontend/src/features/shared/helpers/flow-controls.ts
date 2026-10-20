import { onMounted, watch, type WatchSource } from 'vue'
import { useI18n } from 'vue-i18n'

/** Classe dei pulsanti dei controlli di vue-flow -> chiave i18n dell'etichetta. */
const CONTROL_LABELS: Record<string, string> = {
  'vue-flow__controls-zoomin': 'flow.zoomIn',
  'vue-flow__controls-zoomout': 'flow.zoomOut',
  'vue-flow__controls-fitview': 'flow.fitView',
  'vue-flow__controls-interactive': 'flow.interactive',
}

/**
 * Dà un nome accessibile ai pulsanti dei controlli di vue-flow (`<Controls>` non lo espone: sono solo icone).
 * Da chiamare nel setup della pagina che li contiene; opera sul DOM al montaggio e a ogni cambio di `source`
 * (i controlli compaiono solo dopo il caricamento dei dati).
 *
 * @param source - dato che, cambiando, puo' far comparire i controlli (es. i nodi del grafo)
 */
export function useFlowControlLabels(source: WatchSource): void {
  const { t } = useI18n()
  const label = (): void => {
    for (const [cls, key] of Object.entries(CONTROL_LABELS)) {
      document.querySelectorAll<HTMLElement>(`.${cls}`).forEach((el) => {
        el.setAttribute('aria-label', t(key))
        el.setAttribute('title', t(key))
      })
    }
  }
  onMounted(label)
  watch(source, label, { flush: 'post' })
}
