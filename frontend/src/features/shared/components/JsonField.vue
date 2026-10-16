<template>
  <q-input
    v-model="text"
    type="textarea"
    autogrow
    outlined
    dense
    stack-label
    input-class="pachi-json-field"
    :label="label"
    :hint="error || hint"
    :error="!!error"
    :readonly="readonly"
    @update:model-value="onInput"
  />
</template>

<script setup lang="ts">
/**
 * Editor JSON di ripiego per i valori di `extra` di forma sconosciuta (oggetti, liste non di stringhe, `null`).
 * Emette il valore già interpretato solo se il testo è JSON valido; `validate()` segnala l'errore.
 */
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const props = withDefaults(
  defineProps<{
    modelValue?: unknown
    label?: string
    hint?: string
    readonly?: boolean
  }>(),
  { label: '', hint: '', readonly: false },
)

const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()
const { t } = useI18n()

/**
 * Testo da mostrare per un valore.
 *
 * @param value - valore del campo
 */
function format(value: unknown): string {
  return value === undefined ? '' : JSON.stringify(value, null, 2)
}

const text = ref(format(props.modelValue))
const error = ref('')

// Reset / ricarica del record: riallinea il testo solo se il valore non coincide con quello digitato.
watch(
  () => props.modelValue,
  (value) => {
    try {
      if (JSON.stringify(JSON.parse(text.value)) === JSON.stringify(value)) return
    } catch {
      // testo non valido: lo sostituisce il valore esterno
    }
    text.value = format(value)
    error.value = ''
  },
)

/**
 * Interpreta il testo digitato; un testo vuoto vale `undefined` (campo non impostato).
 *
 * @param raw - testo del campo
 */
function onInput(raw: string | number | null): void {
  const source = String(raw ?? '')
  if (source.trim() === '') {
    error.value = ''
    emit('update:modelValue', undefined)
    return
  }
  try {
    const parsed: unknown = JSON.parse(source)
    error.value = ''
    emit('update:modelValue', parsed)
  } catch {
    error.value = t('extra.jsonInvalid')
  }
}

/** Valida il testo corrente (usato dal form prima del salvataggio). */
function validate(): boolean {
  if (text.value.trim() === '') return true
  try {
    JSON.parse(text.value)
    error.value = ''
    return true
  } catch {
    error.value = t('extra.jsonInvalid')
    return false
  }
}

defineExpose({ validate })
</script>

<style lang="scss">
.pachi-json-field {
  font-family: var(--pachi-mono, monospace);
  font-size: 12px;
}
</style>
