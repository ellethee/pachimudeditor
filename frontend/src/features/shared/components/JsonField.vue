<template>
  <div class="pachi-json-field">
    <div v-if="label" class="text-caption text-grey-7 q-mb-xs">{{ label }}</div>
    <code-editor v-model="text" language="json" height="8em" :readonly="readonly" :error="error" @update:model-value="onInput" />
    <div v-if="hint && !error" class="text-caption text-grey-7 q-mt-xs">{{ hint }}</div>
  </div>
</template>

<script setup lang="ts">
/**
 * Editor JSON (CodeEditor) di ripiego per i valori di `extra` di forma sconosciuta (oggetti, liste non di stringhe, `null`).
 * Emette il valore già interpretato solo se il testo è JSON valido; `validate()` segnala l'errore.
 */
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import CodeEditor from './CodeEditor.vue'

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
function onInput(source: string): void {
  if (source.trim() === '') {
    error.value = ''
    emit('update:modelValue', undefined)
    return
  }
  try {
    const parsed: unknown = JSON.parse(source)
    error.value = ''
    emit('update:modelValue', parsed)
  } catch (e) {
    error.value = parseError(e)
  }
}

/**
 * Messaggio di errore di parsing (con riga/colonna se il motore JS le fornisce).
 *
 * @param e - eccezione di `JSON.parse`
 */
function parseError(e: unknown): string {
  return `${t('extra.jsonInvalid')} (${e instanceof Error ? e.message : String(e)})`
}

/** Valida il testo corrente (usato dal form prima del salvataggio). */
function validate(): boolean {
  if (text.value.trim() === '') return true
  try {
    JSON.parse(text.value)
    error.value = ''
    return true
  } catch (e) {
    error.value = parseError(e)
    return false
  }
}

defineExpose({ validate })
</script>
