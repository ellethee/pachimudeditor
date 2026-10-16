import { nextTick, watch } from 'vue'

/**
 * Attende che un valore reattivo (es. il ref della tabella, montata dopo il caricamento dei lookup) sia
 * disponibile. Usato dai deep-link che aprono un editor appena la pagina è pronta.
 *
 * @param getter - lettura del valore (`undefined`/`null` = non ancora pronto)
 * @returns il valore, appena presente
 */
export function whenReady<T>(getter: () => T | null | undefined): Promise<T> {
  return new Promise<T>((resolve) => {
    const stop = watch(
      getter,
      (value) => {
        if (value === null || value === undefined) return
        // `stop` non esiste ancora se il valore è già pronto alla prima valutazione sincrona
        void nextTick(() => stop())
        resolve(value)
      },
      { immediate: true, flush: 'post' },
    )
  })
}
