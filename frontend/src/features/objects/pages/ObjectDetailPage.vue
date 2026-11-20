<template>
  <div class="q-pa-md">
    <div class="row items-center q-mb-md q-gutter-md">
      <q-btn flat round :icon="mdiArrowLeft" :to="backTo" :aria-label="t('objects.detail.back')">
        <q-tooltip>{{ t('objects.detail.back') }}</q-tooltip>
      </q-btn>
      <h1 class="text-h5 q-my-none">{{ object ? `#${object.vnum} — ${object.shortDescription}` : t('objects.detail.title') }}</h1>
      <q-space />
      <q-btn v-if="object && !readOnly && !guardOf(object.extra).corrupted" outline color="negative" no-caps :icon="mdiDelete" :label="t('objects.detail.remove')" @click="remove" />
    </div>

    <q-banner v-if="failed" rounded class="bg-negative text-white" data-testid="object-not-found">{{ t('objects.detail.notFound') }}</q-banner>

    <div v-else-if="object && form" class="row q-col-gutter-lg">
      <div class="col-12 col-lg-8">
        <sections-form
          :key="formKey"
          ref="formRef"
          :sections="form.sections"
          :readonly="form.locked"
          :saving="saving"
          :error="saveError"
          @save="save"
        />
      </div>
      <div class="col-12 col-lg-4">
        <q-card flat bordered>
          <q-card-section class="text-h6">{{ t('objects.detail.references') }}</q-card-section>
          <q-separator />
          <q-list dense>
            <q-item-label header>{{ t('objects.detail.resets', { count: usage.length }) }}</q-item-label>
            <q-item v-for="(use, i) in usage" :key="i" clickable :to="useLink(use)">
              <q-item-section>
                <q-item-label>{{ use.zoneName }}</q-item-label>
                <q-item-label caption>{{ use.source === 'exit_key' ? t('objects.detail.exitKey', { vnum: use.roomVnum }) : `#${(use.orderIndex ?? 0) + 1}` }}</q-item-label>
              </q-item-section>
            </q-item>
            <q-item v-if="usage.length === 0"><q-item-section class="text-grey">{{ t('objects.detail.none') }}</q-item-section></q-item>
          </q-list>
        </q-card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * Dettaglio oggetto: maschera di modifica inline (le stesse sezioni del dialogo di creazione) e pannello dei riferimenti
 * (comandi di reset e uscite che lo usano).
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'
import { mdiArrowLeft, mdiDelete } from '@quasar/extras/mdi-v7'
import { loadObjectEnums, useObjectForm } from '../composables/use-object-form'
import { describeError } from '../helpers/describe-error'
import { deleteObject, getObject, getObjectUsage, updateObject } from '../services/objects-api'
import type { IObjectEnums, IObjects, IResetUsage } from '../types/objects'
import SectionsForm from '../../shared/components/SectionsForm.vue'
import { guardOf } from '../../shared/helpers/record-guard'
import { useWorld } from '../../shared/helpers/world-state'

const { t } = useI18n()
const $q = useQuasar()
const route = useRoute()
const router = useRouter()
const { readOnly } = useWorld()
const { prepareObjectForm } = useObjectForm()

const objectId = computed(() => Number(route.params.id))
const object = ref<IObjects | null>(null)
const failed = ref(false)
const usage = ref<IResetUsage[]>([])
const form = ref<Awaited<ReturnType<typeof prepareObjectForm>> | null>(null)
const formKey = ref(0)
const formRef = ref<{ commit: () => void; hasChanges: () => boolean } | null>(null)
const saving = ref(false)
const saveError = ref('')
let enums: IObjectEnums | null = null

const backTo = computed(() => ({ path: '/objects', query: object.value ? { zoneId: String(object.value.zoneId) } : {} }))

/**
 * Dove porta un riferimento: la stanza per le chiavi di uscita, altrimenti lo script di reset della zona.
 * @param use riferimento
 */
function useLink(use: IResetUsage): RouteLocationRaw {
  return use.source === 'exit_key' && use.roomId ? `/rooms/${use.roomId}` : { path: `/zones/${use.zoneId}`, query: { tab: 'resets' } }
}

/** Carica l'oggetto, riferimenti e form (nuova `key` = rimonta le sezioni con la nuova base). */
async function load(): Promise<void> {
  failed.value = false
  try {
    enums ??= await loadObjectEnums()
    object.value = await getObject(objectId.value)
  } catch {
    object.value = null
    form.value = null
    failed.value = true
    return
  }
  form.value = await prepareObjectForm(enums, object.value)
  formKey.value++
  usage.value = await getObjectUsage(objectId.value).catch(() => [])
}

/**
 * Salva l'oggetto (PUT = patch parziale: vnum e zona non si cambiano).
 * @param results risultati delle sezioni
 */
async function save(results: Record<string, unknown>): Promise<void> {
  if (!form.value) return
  const { vnum: _vnum, ...patch } = form.value.collect(results)
  saving.value = true
  saveError.value = ''
  try {
    await updateObject(objectId.value, patch)
    formRef.value?.commit()
    $q.notify({ type: 'positive', message: t('objects.detail.saved') })
    await load()
  } catch (error) {
    saveError.value = await describeError(error)
  } finally {
    saving.value = false
  }
}

/** Elimina l'oggetto dopo conferma, con avviso se è usato dai reset. */
function remove(): void {
  if (!object.value) return
  const { shortDescription, vnum, zoneId } = object.value
  const zones = [...new Set(usage.value.map((u) => u.zoneName))].join(', ')
  const warning = usage.value.length > 0 ? ' ' + t('objects.delete.usageWarning', { count: usage.value.length, zones }) : ''
  $q.dialog({ title: t('objects.delete.title'), message: t('objects.delete.message', { name: shortDescription, vnum }) + warning, cancel: true, persistent: true }).onOk(async () => {
    try {
      await deleteObject(objectId.value)
      formRef.value?.commit()
      await router.push({ path: '/objects', query: { zoneId: String(zoneId) } })
    } catch {
      // già segnalato dal client HTTP
    }
  })
}

/** Conferma l'uscita con modifiche non salvate. */
function confirmLeave(): Promise<boolean> | boolean {
  if (!formRef.value?.hasChanges()) return true
  return new Promise((resolve) => {
    $q.dialog({
      title: t('zones.detail.unsavedTitle'),
      message: t('zones.detail.unsavedMessage'),
      cancel: true,
      persistent: true,
      ok: { label: t('zones.resets.discard'), flat: true, color: 'negative' },
    })
      .onOk(() => resolve(true))
      .onCancel(() => resolve(false))
      .onDismiss(() => resolve(false))
  })
}
onBeforeRouteLeave(confirmLeave)
onBeforeRouteUpdate((to, from) => (to.params.id === from.params.id ? true : confirmLeave()))

// uscendo dalla pagina l'id della route sparisce (NaN): non ricaricare
watch(objectId, (id) => Number.isFinite(id) && void load())
onMounted(load)
</script>
