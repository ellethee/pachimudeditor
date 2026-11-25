<template>
  <div ref="host" class="yaml-editor" :class="{ 'yaml-editor--dark': $q.dark.isActive }" :style="{ minHeight: height }" />
</template>

<script setup lang="ts">
/**
 * Editor YAML (CodeMirror 6, caricato in lazy). Con `schema` (JSON Schema) sottolinea gli errori con il messaggio, completa chiavi e
 * valori `enum` e mostra la `description` in hover; senza schema è un semplice editor YAML con colori e numeri di riga.
 * Il testo è `v-model`; il tema segue `$q.dark`. Se il caricamento fallisce resta un riquadro vuoto (il testo non si perde: è nel modello).
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
    /** Testo YAML. */
    modelValue: string
    /** JSON Schema per validazione, completamento e hover (assente = solo sintassi). */
    schema?: object | null
    readonly?: boolean
    /** Altezza minima CSS dell'editor. */
    height?: string
  }>(),
  { schema: null, readonly: false, height: '16em' },
)
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const $q = useQuasar()

const host = shallowRef<HTMLElement | null>(null)
const view = shallowRef<EditorView | null>(null)
const mode = shallowRef<Compartment | null>(null)
const lang = shallowRef<Compartment | null>(null)

onMounted(async () => {
  const [{ EditorView, keymap, lineNumbers, highlightActiveLine, drawSelection, tooltips }, { EditorState, Compartment }, cmds, language, lint, ac, yamlLang, yamlSchema] = await Promise.all([
    import('@codemirror/view'),
    import('@codemirror/state'),
    import('@codemirror/commands'),
    import('@codemirror/language'),
    import('@codemirror/lint'),
    import('@codemirror/autocomplete'),
    import('@codemirror/lang-yaml'),
    import('codemirror-json-schema/yaml'),
  ])
  if (!host.value) return
  mode.value = new Compartment()
  lang.value = new Compartment()
  const schemaExt = (): unknown[] => (props.schema ? yamlSchema.yamlSchema(inlineRefs(props.schema) as JSONSchema7) : [yamlLang.yaml()])
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
        language.syntaxHighlighting(language.defaultHighlightStyle, { fallback: true }),
        ac.autocompletion(),
        keymap.of([...cmds.defaultKeymap, ...cmds.historyKeymap, ...ac.completionKeymap, ...lint.lintKeymap]),
        EditorView.lineWrapping,
        mode.value.of([EditorState.readOnly.of(props.readonly), EditorView.editable.of(!props.readonly)]),
        lang.value.of(schemaExt() as never),
        EditorView.updateListener.of((u) => {
          if (u.docChanged) emit('update:modelValue', u.state.doc.toString())
        }),
      ],
    }),
  })
})

watch(
  () => props.modelValue,
  (value) => {
    const v = view.value
    if (v && value !== v.state.doc.toString()) v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: value } })
  },
)

watch(
  () => props.schema,
  async (schema) => {
    const v = view.value
    if (!v || !lang.value) return
    const [yamlLang, yamlSchema] = await Promise.all([import('@codemirror/lang-yaml'), import('codemirror-json-schema/yaml')])
    v.dispatch({ effects: lang.value.reconfigure(schema ? yamlSchema.yamlSchema(inlineRefs(schema) as JSONSchema7) : [yamlLang.yaml()]) })
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

onBeforeUnmount(() => view.value?.destroy())
</script>

<style>
.yaml-editor {
  border: 1px solid rgba(0, 0, 0, 0.24);
  border-radius: 4px;
  font-size: 13px;
}
.yaml-editor .cm-editor {
  min-height: inherit;
  background: #fff;
  color: #212121;
}
.yaml-editor .cm-editor.cm-focused {
  outline: 2px solid var(--q-primary);
}
.yaml-editor .cm-gutters {
  background: #f5f5f5;
  color: #757575;
  border-right: 1px solid #e0e0e0;
}
.yaml-editor .cm-scroller {
  font-family: monospace;
}
.yaml-editor .cm-tooltip {
  max-width: min(60ch, 90vw);
}
.yaml-editor--dark {
  border-color: rgba(255, 255, 255, 0.28);
}
.yaml-editor--dark .cm-editor {
  background: #1d1d1d;
  color: #e0e0e0;
}
.yaml-editor--dark .cm-gutters {
  background: #262626;
  color: #9e9e9e;
  border-color: #424242;
}
.yaml-editor--dark .cm-activeLine {
  background: rgba(255, 255, 255, 0.06);
}
.yaml-editor--dark .cm-tooltip {
  background: #2b2b2b;
  color: #e0e0e0;
  border-color: #555;
}
</style>
