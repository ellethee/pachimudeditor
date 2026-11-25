import type { Directive } from 'vue'

/** Opzioni di `v-fit-height`. */
export interface IFitHeightOptions {
  /** Spazio (px) da lasciare sotto l'elemento, oltre agli eventuali fratelli successivi. Default 16. */
  offset?: number
  /** Altezza minima in px sotto cui non scendere. Default 240. */
  min?: number
}

interface IFitState {
  fit: () => void
  observer?: ResizeObserver
}

const states = new WeakMap<HTMLElement, IFitState>()

/**
 * Direttiva `v-fit-height`: porta l'altezza dell'elemento dal suo bordo alto al fondo della finestra
 * (`100vh - top - offset - altezza dei fratelli successivi`), così il contenuto interno scorre invece di sforare la pagina.
 * Si ricalcola al ridimensionamento della finestra e quando cambia il layout del genitore (stessa logica dell'auto-height di PachiTable2).
 *
 * @example `<q-card v-fit-height="{ offset: 24 }" class="column no-wrap">`
 */
export const vFitHeight: Directive<HTMLElement, IFitHeightOptions | undefined> = {
  mounted(el, binding) {
    let timer: ReturnType<typeof setTimeout> | undefined
    const fit = (): void => {
      clearTimeout(timer)
      timer = setTimeout(() => {
        const opts = binding.value ?? {}
        let below = opts.offset ?? 16
        for (let sib = el.nextElementSibling as HTMLElement | null; sib; sib = sib.nextElementSibling as HTMLElement | null) {
          below += sib.getBoundingClientRect().height
        }
        const height = Math.max(opts.min ?? 240, window.innerHeight - el.getBoundingClientRect().top - below)
        el.style.height = `${height}px`
      }, 50)
    }
    const state: IFitState = { fit }
    if (el.parentElement && typeof ResizeObserver !== 'undefined') {
      state.observer = new ResizeObserver(fit)
      state.observer.observe(el.parentElement)
    }
    window.addEventListener('resize', fit)
    states.set(el, state)
    fit()
  },
  updated(el) {
    states.get(el)?.fit()
  },
  unmounted(el) {
    const state = states.get(el)
    if (!state) return
    window.removeEventListener('resize', state.fit)
    state.observer?.disconnect()
    states.delete(el)
  },
}
