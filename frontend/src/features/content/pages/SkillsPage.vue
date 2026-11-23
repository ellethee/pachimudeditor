<template>
  <div class="q-pa-md column q-gutter-y-md">
    <content-live-bar ref="bar" kind="skills" />
    <div class="row q-col-gutter-lg">
      <div class="col-12 col-md-5">
        <content-item-list
          :rows="listRows"
          :selected="selectedId"
          :loading="loading"
          :create-label="t('content.skills.create')"
          testid="skills-list"
          @select="select"
          @create="startCreate"
        />
      </div>
      <div class="col-12 col-md-7">
        <q-card v-if="form" flat bordered class="q-pa-md" data-testid="skill-form">
          <div class="row items-center q-mb-sm">
            <div class="text-h6">{{ creating ? t('content.skills.createTitle') : selectedId }}</div>
            <span v-if="!creating && displayNames" class="q-ml-md text-grey-8" data-testid="skill-names">{{ displayNames }}</span>
            <q-badge v-if="!creating && layer === 'base'" class="q-ml-md" color="grey" outline :label="t('content.layer.baseHint')" />
            <q-space />
            <q-btn
              v-if="!creating && layer === 'user'"
              flat
              no-caps
              color="negative"
              :icon="mdiDelete"
              :label="t('content.actions.delete')"
              :disable="readOnly"
              data-testid="skill-delete"
              @click="remove"
            />
          </div>
          <sections-form :key="formKey" ref="formRef" :sections="form" :readonly="readOnly" :saving="saving" :error="saveError" @save="save" />
        </q-card>
        <q-banner v-else rounded class="bg-grey-2">{{ t('content.skills.pick') }}</q-banner>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * Skill (incantesimi e abilità, `skills/*.yaml` a strati): elenco e maschera inline. I campi semplici sono nel form; effetti, livelli,
 * messaggi e il resto si modificano come YAML. Modificare una skill di serie ne crea la copia nello strato dell'utente. Dopo il
 * salvataggio il gioco (se il canale live c'è) controlla i file e i problemi compaiono nel pannello.
 */
import { computed, markRaw, nextTick, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import { mdiDelete } from '@quasar/extras/mdi-v7'
import { FieldsSection } from '@ilpachi/pachi-kit/fields'
import type { ISectionDefinition } from '@ilpachi/pachi-kit/edit-dialog'
import type { IFieldRow } from '@ilpachi/pachi-kit/fields'
import ContentItemList from '../components/ContentItemList.vue'
import ContentLiveBar from '../components/ContentLiveBar.vue'
import SectionsForm from '../../shared/components/SectionsForm.vue'
import { useWorld } from '../../shared/helpers/world-state'
import { describeError } from '../helpers/describe-error'
import { buildSkillRows, formToSkill, skillToForm } from '../helpers/skill-rows'
import { createSkill, deleteSkill, getSkill, listSkills, updateSkill } from '../services/content-files-api'
import type { ISkill } from '../types/content-files'

const { t } = useI18n()
const $q = useQuasar()
const { readOnly } = useWorld()

const skills = ref<ISkill[]>([])
const loading = ref(false)
const selectedId = ref<string | null>(null)
const creating = ref(false)
const layer = ref<'user' | 'base'>('base')
const form = ref<ISectionDefinition[] | null>(null)
const formKey = ref(0)
const formRef = ref<{ commit: () => void; hasChanges: () => boolean } | null>(null)
const bar = ref<InstanceType<typeof ContentLiveBar> | null>(null)
const saving = ref(false)
const saveError = ref('')
/** La skill aperta com'era (serve a distinguere i campi cambiati da quelli solo mostrati). */
let loadedSkill: ISkill | null = null

/** I nomi mostrati ai giocatori (`messages.name`) della skill aperta, es. «it: Getto acido · en: acid blast». */
const displayNames = computed(() => {
  const skill = skills.value.find((s) => s.skillId === selectedId.value)
  return Object.entries(skill?.names ?? {})
    .map(([lang, name]) => `${lang}: ${name}`)
    .join(' · ')
})

const listRows = computed(() =>
  skills.value.map((s) => ({
    id: s.skillId,
    info: [s.kind, s.names?.it ?? (s.name && s.name !== s.skillId ? s.name : ''), Object.keys(s.levels ?? {}).length ? `${Object.keys(s.levels ?? {}).length} cl.` : '']
      .filter(Boolean)
      .join(' · '),
    layer: s.layer,
    error: s.error,
  })),
)

/** Carica l'elenco. */
async function load(): Promise<void> {
  loading.value = true
  try {
    skills.value = await listSkills()
  } catch (error) {
    $q.notify({ type: 'negative', message: await describeError(error) })
  } finally {
    loading.value = false
  }
}

/** Costruisce le sezioni del form con i valori iniziali. */
function buildForm(skill: ISkill | null): void {
  loadedSkill = skill
  const rows = buildSkillRows(t, !!skill)
  const initial = skillToForm(skill)
  const section = (key: string, title: string, sectionRows: IFieldRow[], order: number): ISectionDefinition => ({
    key,
    title,
    component: markRaw(FieldsSection),
    props: { rows: sectionRows },
    initialValue: initial,
    order,
    container: { type: 'expansion', title, defaultOpened: true },
  })
  form.value = [
    section('general', t('content.skills.sections.general'), rows.general, 10),
    section('advanced', t('content.skills.sections.advanced'), rows.advanced, 20),
  ]
  formKey.value++
}

/** Chiede conferma se ci sono modifiche non salvate. */
function confirmDiscard(): Promise<boolean> {
  if (!formRef.value?.hasChanges()) return Promise.resolve(true)
  return new Promise((resolve) => {
    $q.dialog({ title: t('content.unsavedTitle'), message: t('content.unsavedMessage'), cancel: true, persistent: true })
      .onOk(() => resolve(true))
      .onCancel(() => resolve(false))
      .onDismiss(() => resolve(false))
  })
}

/** Apre una skill nella maschera. */
async function select(id: string): Promise<void> {
  if (id === selectedId.value && !creating.value) return
  if (!(await confirmDiscard())) return
  saveError.value = ''
  try {
    const skill = await getSkill(id)
    if (skill.error) {
      $q.notify({ type: 'negative', message: skill.error })
      return
    }
    creating.value = false
    selectedId.value = id
    layer.value = skill.layer
    buildForm(skill)
  } catch (error) {
    $q.notify({ type: 'negative', message: await describeError(error) })
  }
}

/** Apre la maschera di creazione. */
async function startCreate(): Promise<void> {
  if (!(await confirmDiscard())) return
  saveError.value = ''
  creating.value = true
  selectedId.value = null
  layer.value = 'user'
  buildForm(null)
}

/** Salva (crea o aggiorna) e fa controllare i file al gioco. */
async function save(results: Record<string, unknown>): Promise<void> {
  const values = Object.assign({}, ...Object.values(results)) as Record<string, unknown>
  const body = formToSkill(values, !creating.value, loadedSkill)
  saving.value = true
  saveError.value = ''
  try {
    const saved = creating.value ? await createSkill(body) : await updateSkill(selectedId.value as string, body)
    formRef.value?.commit()
    $q.notify({ type: 'positive', message: t('content.savedLayered') })
    await load()
    creating.value = false
    selectedId.value = saved.skillId
    layer.value = saved.layer
    buildForm(saved)
    await nextTick()
    await bar.value?.validate()
  } catch (error) {
    saveError.value = await describeError(error)
  } finally {
    saving.value = false
  }
}

/** Elimina la skill dallo strato dell'utente dopo conferma (torna quella di serie, se c'è). */
function remove(): void {
  const id = selectedId.value
  if (!id) return
  $q.dialog({ title: t('content.deleteTitle'), message: t('content.skills.deleteConfirm', { id }), cancel: true, persistent: true }).onOk(async () => {
    try {
      await deleteSkill(id)
      formRef.value?.commit()
      form.value = null
      selectedId.value = null
      await load()
      await bar.value?.validate()
    } catch (error) {
      $q.notify({ type: 'negative', message: await describeError(error) })
    }
  })
}

onMounted(load)
</script>
