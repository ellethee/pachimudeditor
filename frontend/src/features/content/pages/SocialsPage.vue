<template>
  <div class="q-pa-md column q-gutter-y-md">
    <content-live-bar ref="bar" kind="socials" />
    <div class="row q-col-gutter-lg">
      <div class="col-12 col-md-4">
        <content-item-list
          :rows="listRows"
          :selected="selectedId"
          :loading="loading"
          :create-label="t('content.socials.create')"
          testid="socials-list"
          @select="select"
          @create="startCreate"
        />
      </div>
      <div class="col-12 col-md-8">
        <q-card v-if="form" flat bordered class="q-pa-md" data-testid="social-form">
          <div class="row items-center q-mb-sm">
            <div class="text-h6">{{ creating ? t('content.socials.createTitle') : selectedId }}</div>
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
              data-testid="social-delete"
              @click="remove"
            />
          </div>
          <sections-form :key="formKey" ref="formRef" :sections="form" :readonly="readOnly" :saving="saving" :error="saveError" @save="save" />
        </q-card>
        <q-banner v-else rounded class="bg-grey-2">{{ t('content.socials.pick') }}</q-banner>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * Social (`tables/socials.yaml` e `socials.<lingua>.yaml`, a strati): elenco e maschera inline con i testi per lingua. Si scrive
 * sempre nello strato dell'utente (tutte le lingue nella voce del social); eliminarlo ripristina quello di serie, se c'è.
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
import { SOCIAL_LANGS, buildSocialRows, formToSocial, socialToForm } from '../helpers/skill-rows'
import { createSocial, deleteSocial, listSocials, updateSocial } from '../services/content-files-api'
import type { ISocial } from '../types/content-files'

const { t } = useI18n()
const $q = useQuasar()
const { readOnly } = useWorld()

const socials = ref<ISocial[]>([])
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

/** Lingue mostrate: it ed en più quelle presenti in qualche social. */
const langs = computed(() => [...new Set([...SOCIAL_LANGS, ...socials.value.flatMap((s) => Object.keys(s.messages))])])
const listRows = computed(() =>
  socials.value.map((s) => ({
    id: s.name,
    info: [s.position, s.hide ? t('content.socials.hidden') : '', s.aliases.length ? s.aliases.join(', ') : ''].filter(Boolean).join(' · '),
    layer: s.layer,
  })),
)

/** Carica l'elenco. */
async function load(): Promise<void> {
  loading.value = true
  try {
    socials.value = await listSocials()
  } catch (error) {
    $q.notify({ type: 'negative', message: await describeError(error) })
  } finally {
    loading.value = false
  }
}

/** Costruisce le sezioni del form (una per le generalità, una per lingua). */
function buildForm(social: ISocial | null): void {
  const rows = buildSocialRows(t, !!social, langs.value)
  const initial = socialToForm(social, langs.value)
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
    section('general', t('content.socials.sections.general'), rows.general, 10),
    ...langs.value.map((lang, i) => section(`lang-${lang}`, t('content.socials.sections.lang', { lang }), rows.langs[lang] ?? [], 20 + i)),
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

/** Apre un social nella maschera. */
async function select(id: string): Promise<void> {
  if (id === selectedId.value && !creating.value) return
  if (!(await confirmDiscard())) return
  const social = socials.value.find((s) => s.name === id)
  if (!social) return
  saveError.value = ''
  creating.value = false
  selectedId.value = id
  layer.value = social.layer
  buildForm(social)
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
  const body = formToSocial(values, langs.value)
  const name = creating.value ? String(values.name ?? '').trim() : (selectedId.value as string)
  saving.value = true
  saveError.value = ''
  try {
    const saved = creating.value ? await createSocial(name, body) : await updateSocial(name, body)
    formRef.value?.commit()
    $q.notify({ type: 'positive', message: t('content.savedLayered') })
    await load()
    creating.value = false
    selectedId.value = saved.name
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

/** Toglie il social dallo strato dell'utente dopo conferma. */
function remove(): void {
  const id = selectedId.value
  if (!id) return
  $q.dialog({ title: t('content.deleteTitle'), message: t('content.socials.deleteConfirm', { id }), cancel: true, persistent: true }).onOk(async () => {
    try {
      await deleteSocial(id)
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
