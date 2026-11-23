<template>
  <q-select
    ref="select"
    :model-value="modelValue"
    :options="shown"
    multiple
    use-chips
    use-input
    input-debounce="0"
    new-value-mode="add-unique"
    outlined
    dense
    stack-label
    :label="label"
    :hint="hint"
    :readonly="readonly"
    @filter="filter"
    @add="onAdd"
    @keydown.enter="byEnter = true"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template v-if="details" #option="{ itemProps, opt }">
      <q-item v-bind="itemProps" :data-testid="`flag-option-${opt}`">
        <q-item-section>
          <q-item-label>
            {{ opt }}
            <q-badge v-if="details[opt]?.implemented === false" color="orange" outline class="q-ml-sm">{{ t('extra.flagInactive') }}</q-badge>
            <q-badge v-if="details[opt]?.origin" color="grey" outline class="q-ml-xs">{{ details[opt]?.origin }}</q-badge>
          </q-item-label>
          <q-item-label v-if="describe(opt)" caption>{{ describe(opt) }}</q-item-label>
        </q-item-section>
      </q-item>
    </template>
  </q-select>
</template>

<script setup lang="ts">
/**
 * Campo "flag" con elenco di nomi noti (tabelle ROM di `/api/meta/enums` o catalogo del gioco): si sceglie
 * dall'elenco filtrabile; un valore non in elenco si può comunque aggiungere con Invio (il gioco lo segnala).
 * Con `details` (catalogo pachimud) ogni voce mostra la descrizione nella lingua dell'interfaccia, gli alias,
 * l'origine e un'etichetta «non ancora attivo» se il gioco non usa quel flag.
 * Componente custom di `FieldsSection`, alternativa a `FlagsField` (testo libero) quando il descrittore del
 * campo dichiara un `enum`.
 */
import { ref, watch } from 'vue'
import type { QSelect } from 'quasar'
import { useI18n } from 'vue-i18n'
import type { IFlagDetail } from '../helpers/descriptor-rows'

const props = withDefaults(
  defineProps<{
    modelValue?: string[]
    /** Nomi ammessi. */
    options?: string[]
    /** Spiegazione di ogni nome (facoltativa). */
    details?: Record<string, IFlagDetail>
    label?: string
    hint?: string
    readonly?: boolean
  }>(),
  { modelValue: () => [], options: () => [], label: '', hint: '', readonly: false },
)

const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()
const { t, locale } = useI18n()

const select = ref<QSelect | null>(null)
const shown = ref<string[]>(props.options)
/** Un valore aggiunto con Invio chiude il menu delle opzioni, che altrimenti resterebbe sopra i campi sotto (con il mouse resta aperto per sceglierne altri). */
let byEnter = false
watch(
  () => props.options,
  (options) => (shown.value = options),
)

/**
 * Descrizione di un flag nella lingua corrente, con gli alias accettati.
 *
 * @param name - nome del flag
 * @returns testo da mostrare sotto il nome ('' se il mondo non lo spiega)
 */
function describe(name: string): string {
  const detail = props.details?.[name]
  const text = detail?.description?.[locale.value.startsWith('en') ? 'en' : 'it'] ?? ''
  const aliases = detail?.aliases?.length ? ` (${t('extra.flagAliases')}: ${detail.aliases.join(', ')})` : ''
  return text + aliases
}

/**
 * Filtra le opzioni in base al testo digitato (nome o alias).
 *
 * @param text - testo digitato
 * @param update - callback di Quasar per applicare l'elenco filtrato
 */
function filter(text: string, update: (fn: () => void) => void): void {
  update(() => {
    const needle = text.toLowerCase()
    shown.value = props.options.filter(
      (option) => option.toLowerCase().includes(needle) || props.details?.[option]?.aliases?.some((a) => a.toLowerCase().includes(needle)),
    )
  })
}

/** Un valore e' stato aggiunto: se con Invio, chiude il menu delle opzioni. */
function onAdd(): void {
  // dopo l'evento Quasar svuota l'input e puo' riaprire il menu: lo si chiude a giro finito
  if (byEnter) setTimeout(() => select.value?.hidePopup(), 0)
  byEnter = false
}
</script>
