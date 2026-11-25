<template>
  <div :class="{ 'code-editor-fill': fill }">
    <div ref="host" class="code-editor" :class="{ 'code-editor--dark': $q.dark.isActive, 'code-editor--error': !!error }" :style="{ minHeight: fill ? '8em' : height }" />
    <div v-if="error" class="text-negative text-caption q-mt-xs" data-testid="code-editor-error">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
/**
 * Editor di codice (CodeMirror 6, caricato in lazy) per YAML, JSON o testo semplice (`language`). Con `schema` (JSON Schema; solo
 * yaml/json) sottolinea gli errori con il messaggio, completa chiavi e valori `enum` e mostra la `description` in hover; senza schema
 * colora e (json) segnala gli errori di sintassi. `error` è un messaggio di errore del genitore (es. «riga 3, colonna 5: ...»).
 * Il testo è `v-model` (nessuna logica di salvataggio qui); il tema segue `$q.dark`. Se il caricamento fallisce resta un riquadro vuoto (il testo non si perde: è nel modello).
 */
import { onBeforeUnmount, onMounted, shallowRef, watch } from 'vue'
import type { EditorView } from '@codemirror/view'
import type { Compartment } from '@codemirror/state'
import { useQuasar } from 'quasar'
import { inlineRefs } from '../helpers/json-schema'

/** JSON Schema accettato da codemirror-json-schema. */
type JSONSchema7 = Parameters<typeof import('codemirror-json-schema/yaml').yamlSchema>[0]

const props = withDefaults(
  defineProps<{
    /** Testo del file. */
    modelValue: string
    /** Linguaggio: `yaml` (default), `json` o `text` (monospace senza colori). */
    language?: 'yaml' | 'json' | 'text'
    /** Errore (di parsing o di salvataggio) da mostrare sotto l'editor, con riga/colonna se il genitore le conosce. */
    error?: string
    /** JSON Schema per validazione, completamento e hover (assente = solo sintassi). */
    schema?: object | null
    readonly?: boolean
    /** Altezza minima CSS dell'editor. */
    height?: string
    /** Riempie lo spazio del genitore (flex) e scorre all'interno invece di crescere col testo. */
    fill?: boolean
  }>(),
  { language: 'yaml', error: '', schema: null, readonly: false, height: '16em', fill: false },
)
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const $q = useQuasar()

/**
 * Estensioni del linguaggio (e dello schema, se c'è).
 *
 * @param language - linguaggio dell'editor
 * @param schema - JSON Schema opzionale
 */
async function languageExtension(language: 'yaml' | 'json' | 'text', schema: object | null): Promise<unknown[]> {
  if (language === 'text') return []
  const resolved = schema ? (inlineRefs(schema) as JSONSchema7) : null
  if (language === 'json') {
    if (resolved) return (await import('codemirror-json-schema')).jsonSchema(resolved) as unknown[]
    const [{ json, jsonParseLinter }, { linter }] = await Promise.all([import('@codemirror/lang-json'), import('@codemirror/lint')])
    return [json(), linter(jsonParseLinter())]
  }
  if (resolved) return (await import('codemirror-json-schema/yaml')).yamlSchema(resolved) as unknown[]
  return [(await import('@codemirror/lang-yaml')).yaml()]
}

const host = shallowRef<HTMLElement | null>(null)
/**
 * Colori della sintassi e modalita' (cursore, selezione) per il tema chiaro o scuro.
 *
 * @param dark - true per il tema scuro
 */
async function themeExtension(dark: boolean): Promise<unknown[]> {
  const [{ HighlightStyle, syntaxHighlighting, defaultHighlightStyle }, { tags: t }, { EditorView }] = await Promise.all([
    import('@codemirror/language'),
    import('@lezer/highlight'),
    import('@codemirror/view'),
  ])
  if (!dark) return [syntaxHighlighting(defaultHighlightStyle, { fallback: true })]
  const style = HighlightStyle.define([
    { tag: [t.propertyName, t.definition(t.propertyName), t.keyword], color: '#82aaff' },
    { tag: [t.string, t.special(t.string)], color: '#c3e88d' },
    { tag: [t.number, t.bool, t.null, t.atom], color: '#f78c6c' },
    { tag: [t.comment, t.meta], color: '#9e9e9e', fontStyle: 'italic' },
    { tag: [t.punctuation, t.separator, t.operator], color: '#b0bec5' },
    { tag: [t.typeName, t.labelName, t.className], color: '#ffcb6b' },
    { tag: t.invalid, color: '#ff5370' },
  ])
  return [EditorView.theme({}, { dark: true }), syntaxHighlighting(style)]
}

const view = shallowRef<EditorView | null>(null)
const mode = shallowRef<Compartment | null>(null)
const lang = shallowRef<Compartment | null>(null)
const theme = shallowRef<Compartment | null>(null)
let langTicket = 0

onMounted(async () => {
  const [{ EditorView, keymap, lineNumbers, highlightActiveLine, drawSelection, tooltips }, { EditorState, Compartment }, cmds, language, lint, ac] = await Promise.all([
    import('@codemirror/view'),
    import('@codemirror/state'),
    import('@codemirror/commands'),
    import('@codemirror/language'),
    import('@codemirror/lint'),
    import('@codemirror/autocomplete'),
  ])
  if (!host.value) return
  mode.value = new Compartment()
  lang.value = new Compartment()
  theme.value = new Compartment()
  view.value = new EditorView({
    parent: host.value,
    state: EditorState.create({
      doc: props.modelValue,
      extensions: [
        lineNumbers(),
        highlightActiveLine(),
        drawSelection(),
        tooltips({ parent: host.value }), // dentro l'host: il tema chiaro/scuro e la larghezza massima si applicano anche ai tooltip
        cmds.history(),
        language.indentOnInput(),
        theme.value.of((await themeExtension($q.dark.isActive)) as never),
        ac.autocompletion(),
        keymap.of([...cmds.defaultKeymap, ...cmds.historyKeymap, ...ac.completionKeymap, ...lint.lintKeymap]),
        EditorView.lineWrapping,
        mode.value.of([EditorState.readOnly.of(props.readonly), EditorView.editable.of(!props.readonly)]),
        lang.value.of((await languageExtension(props.language, props.schema)) as never),
        EditorView.updateListener.of((u) => {
          if (u.docChanged) emit('update:modelValue', u.state.doc.toString())
        }),
      ],
    }),
  })
  lint.forceLinting(view.value)
})

watch(
  () => props.modelValue,
  (value) => {
    const v = view.value
    if (v && value !== v.state.doc.toString()) v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: value } })
  },
)

watch(
  () => [props.schema, props.language] as const,
  async ([schema, language]) => {
    const v = view.value
    if (!v || !lang.value) return
    const ticket = ++langTicket
    const ext = (await languageExtension(language, schema)) as never
    if (ticket !== langTicket) return // un cambio piu' recente e' gia' in corso: scarta il risultato superato
    v.dispatch({ effects: lang.value.reconfigure(ext) })
    // il linter appena configurato non parte da solo sul testo gia' presente: forza il primo controllo
    const { forceLinting } = await import('@codemirror/lint')
    forceLinting(v)
  },
)

watch(
  () => $q.dark.isActive,
  async (dark) => {
    const v = view.value
    if (!v || !theme.value) return
    v.dispatch({ effects: theme.value.reconfigure((await themeExtension(dark)) as never) })
  },
)

watch(
  () => props.readonly,
  async (ro) => {
    const v = view.value
    if (!v || !mode.value) return
    const [{ EditorState }, { EditorView }] = await Promise.all([import('@codemirror/state'), import('@codemirror/view')])
    v.dispatch({ effects: mode.value.reconfigure([EditorState.readOnly.of(ro), EditorView.editable.of(!ro)]) })
  },
)

/**
 * Porta il cursore alla riga (e colonna) indicate, 1-based, e le mostra.
 *
 * @param line - numero di riga
 * @param column - numero di colonna (default 1)
 */
function goToLine(line: number, column = 1): void {
  const v = view.value
  if (!v) return
  const l = v.state.doc.line(Math.min(Math.max(line, 1), v.state.doc.lines))
  const anchor = l.from + Math.min(Math.max(column - 1, 0), l.length)
  v.dispatch({ selection: { anchor }, scrollIntoView: true })
  v.focus()
}
defineExpose({ goToLine })

onBeforeUnmount(() => view.value?.destroy())
</script>

<style>
.code-editor-fill {
  display: flex;
  flex-direction: column;
  flex: 1 1 0;
  min-height: 0;
}
.code-editor-fill > .code-editor {
  flex: 1 1 0;
  min-height: 0;
  overflow: hidden;
}
.code-editor-fill .cm-editor {
  height: 100%;
}
.code-editor-fill .cm-scroller {
  overflow: auto;
}
.code-editor {
  border: 1px solid rgba(0, 0, 0, 0.24);
  border-radius: 4px;
  font-size: 13px;
}
.code-editor .cm-editor {
  min-height: inherit;
  background: #fff;
  color: #212121;
}
.code-editor--error {
  border-color: var(--q-negative);
}
.code-editor .cm-editor.cm-focused {
  outline: 2px solid var(--q-primary);
}
.code-editor .cm-gutters {
  background: #f5f5f5;
  color: #757575;
  border-right: 1px solid #e0e0e0;
}
.code-editor .cm-scroller {
  font-family: monospace;
}
.code-editor .cm-tooltip {
  max-width: min(60ch, 90vw);
}
.code-editor--dark {
  border-color: rgba(255, 255, 255, 0.28);
}
.code-editor--dark .cm-editor {
  background: #1d1d1d;
  color: #e0e0e0;
}
.code-editor--dark .cm-gutters {
  background: #262626;
  color: #9e9e9e;
  border-color: #424242;
}
.code-editor--dark .cm-activeLine {
  background: rgba(255, 255, 255, 0.06);
}
.code-editor--dark .cm-tooltip {
  background: #2b2b2b;
  color: #e0e0e0;
  border-color: #555;
}
</style>
