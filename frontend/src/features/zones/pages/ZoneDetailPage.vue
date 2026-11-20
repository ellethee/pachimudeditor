<template>
  <div class="q-pa-md">
    <div class="row items-center q-mb-md q-gutter-md">
      <q-btn flat round :icon="mdiArrowLeft" to="/zones" :aria-label="t('zones.resets.back')">
        <q-tooltip>{{ t('zones.resets.back') }}</q-tooltip>
      </q-btn>
      <h1 class="text-h5 q-my-none">{{ zone ? `${zone.vnum} — ${zone.name}` : t('zones.detail.title') }}</h1>
      <q-space />
      <q-btn
        v-if="zone && canReload"
        outline
        color="primary"
        :icon="mdiRefresh"
        :label="t('zones.detail.liveReload')"
        :loading="reloading"
        data-testid="zone-live-reload"
        @click="reloadInGame"
      >
        <q-tooltip>{{ t('zones.detail.liveReloadHint') }}</q-tooltip>
      </q-btn>
    </div>

    <q-banner v-if="failed" rounded class="bg-negative text-white" data-testid="zone-not-found">
      {{ t('zones.resets.zoneNotFound') }}
    </q-banner>

    <template v-else-if="zone">
      <q-tabs v-model="tab" dense align="left" class="q-mb-md" active-color="primary" indicator-color="primary">
        <q-tab name="info" :label="t('zones.detail.tabInfo')" data-testid="zone-tab-info" />
        <q-tab v-if="supports('supportsResetScripts')" name="resets" :label="t('zones.detail.tabResets')" data-testid="zone-tab-resets" />
      </q-tabs>

      <q-tab-panels v-model="tab" animated keep-alive class="bg-transparent">
        <q-tab-panel name="info" class="q-pa-none">
          <div class="row q-col-gutter-lg">
            <div class="col-12 col-md-7">
              <sections-form
                v-if="form"
                :key="formKey"
                ref="formRef"
                :sections="form.sections"
                :readonly="form.locked"
                :saving="saving"
                :error="saveError"
                @save="save"
              />
            </div>

            <div class="col-12 col-md-5">
              <q-card v-if="canInstances" flat bordered class="q-mb-md" data-testid="zone-live-instances">
                <q-card-section class="row items-center">
                  <div class="text-h6">{{ t('zones.detail.liveInstances') }}</div>
                  <q-space />
                  <q-btn flat dense round :icon="mdiRefresh" :aria-label="t('zones.detail.liveInstancesRefresh')" data-testid="zone-live-instances-refresh" @click="loadInstances" />
                </q-card-section>
                <q-card-section v-if="instances" class="text-body2">
                  {{ t('zones.detail.liveInstancesCount', { mobs: instanceCount('mob'), objects: instanceCount('obj') }) }}
                  <span v-if="instances.truncated">{{ t('zones.detail.liveInstancesTruncated') }}</span>
                </q-card-section>
              </q-card>
              <q-card flat bordered>
                <q-card-section class="text-h6">{{ t('zones.detail.content') }}</q-card-section>
                <q-card-section v-if="stats" class="row q-col-gutter-md">
                  <div v-for="stat in statRows" :key="stat.label" class="col-6">
                    <div class="text-caption text-grey-7">{{ stat.label }}</div>
                    <div class="text-h4">{{ stat.value }}</div>
                  </div>
                </q-card-section>
                <q-separator />
                <q-list>
                  <q-item v-for="link in links" :key="link.label" clickable :to="link.to">
                    <q-item-section avatar><q-icon :name="link.icon" color="primary" /></q-item-section>
                    <q-item-section class="text-primary">{{ link.label }}</q-item-section>
                  </q-item>
                </q-list>
              </q-card>
            </div>
          </div>
        </q-tab-panel>

        <q-tab-panel v-if="supports('supportsResetScripts')" name="resets" class="q-pa-none">
          <zone-resets-page ref="resets" embedded />
        </q-tab-panel>
      </q-tab-panels>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * Dettaglio zona a tab: **Info** (dati, contenuto con conteggi e link rapidi) e **Reset** (editor dello script).
 * I dati si modificano inline con le stesse sezioni del dialogo di creazione (`useZoneDialogs`).
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { mdiArrowLeft, mdiDoor, mdiMap, mdiRefresh, mdiSkull, mdiSword } from '@quasar/extras/mdi-v7'
import { useZoneDialogs } from '../composables/use-zone-dialogs'
import { getZone, updateZone } from '../services/zones-api'
import { useLive, refreshLiveStatus } from '../../playerfiles/helpers/live-state'
import { getLiveZoneInstances } from '../../playerfiles/services/live-api'
import type { ILiveInstances } from '../../playerfiles/types/live'
import { describeError } from '../utils/errors'
import { useContentLive } from '../../content/composables/use-content-live'
import SectionsForm from '../../shared/components/SectionsForm.vue'
import { useWorld } from '../../shared/helpers/world-state'
import { getWorldOverview } from '../../world/services/world-api'
import type { IZoneOverview } from '../../world/types/world'
import type { IZone } from '../types/zones'
import ZoneResetsPage from './ZoneResetsPage.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { supports } = useWorld()
const { prepareZoneForm, validateRanges } = useZoneDialogs()
const $q = useQuasar()

const live = useLive()
const { reloadZone: reloadZoneLive } = useContentLive()
/** «Ricarica nel gioco»: canale live connesso, scrittura consentita e comando `zone.reload` dichiarato dal gioco (estensione pachimud). */
const canReload = computed(() => live.canWrite.value && (live.status.value?.commands ?? []).includes('zone.reload'))
const reloading = ref(false)
/** Istanze vive della zona: canale connesso e comando `instances.list` dichiarato (estensione pachimud). */
const canInstances = computed(() => live.connected.value && (live.status.value?.commands ?? []).includes('instances.list'))
const instances = ref<ILiveInstances | null>(null)
const zone = ref<IZone | null>(null)
const failed = ref(false)
const stats = ref<IZoneOverview | null>(null)
const resets = ref<{ confirmLeave: () => Promise<boolean> } | null>(null)
const form = ref<Awaited<ReturnType<typeof prepareZoneForm>> | null>(null)
const formKey = ref(0)
const formRef = ref<{ commit: () => void; hasChanges: () => boolean } | null>(null)
const saving = ref(false)
const saveError = ref('')

const zoneId = computed(() => Number(route.params.id))
const tab = ref(route.query.tab === 'resets' ? 'resets' : 'info')

/** Conteggi del contenuto (solo mondi con panoramica). */
const statRows = computed(() =>
  stats.value
    ? [
        { label: t('zones.detail.rooms'), value: stats.value.rooms },
        { label: t('zones.detail.mobs'), value: stats.value.mobs },
        { label: t('zones.detail.objects'), value: stats.value.objects },
        { label: t('zones.detail.resetCommands'), value: stats.value.resetCommands },
      ]
    : [],
)

/** Link rapidi alle liste filtrate per zona. */
const links = computed(() => {
  const query = { zoneId: String(zoneId.value) }
  return [
    { label: t('zones.detail.linkMap'), icon: mdiMap, to: { path: '/rooms/map', query } },
    { label: t('zones.detail.linkRooms'), icon: mdiDoor, to: { path: '/rooms', query } },
    { label: t('zones.detail.linkMobs'), icon: mdiSkull, to: { path: '/mobs', query } },
    { label: t('zones.detail.linkObjects'), icon: mdiSword, to: { path: '/objects', query } },
  ]
})

/** Chiede al gioco acceso di rileggere dai file la zona (dopo il salvataggio) e rifare il reset. */
async function reloadInGame(): Promise<void> {
  if (!zone.value) return
  reloading.value = true
  try {
    if (await reloadZoneLive(zone.value.id)) void loadInstances()
  } finally {
    reloading.value = false
  }
}

/** Rilegge dal gioco le istanze vive della zona (errori ignorati: il dato e' facoltativo). */
async function loadInstances(): Promise<void> {
  if (!zone.value) return
  try {
    instances.value = await getLiveZoneInstances(zone.value.id)
  } catch {
    instances.value = null
  }
}

/** Quante istanze vive di un tipo. */
function instanceCount(kind: 'mob' | 'obj'): number {
  return instances.value?.instances.filter((i) => i.kind === kind).length ?? 0
}

/** Carica la zona e i conteggi (questi ultimi sono facoltativi). */
async function load(): Promise<void> {
  failed.value = false
  try {
    zone.value = await getZone(zoneId.value)
  } catch {
    zone.value = null
    failed.value = true
    return
  }
  await buildForm()
  if (canInstances.value) void loadInstances()
  if (!supports('supportsWorldOverview')) return
  try {
    stats.value = (await getWorldOverview()).zones.find((z) => z.id === zoneId.value) ?? null
  } catch {
    stats.value = null
  }
}

/** Prepara la maschera con i dati correnti della zona (nuova `key` = rimonta le sezioni con la nuova base). */
async function buildForm(): Promise<void> {
  if (!zone.value) return
  form.value = await prepareZoneForm(zone.value)
  formKey.value++
}

/**
 * Salva la zona. In un mondo su file l'id coincide col vnum minimo e cambia con `bottomVnum`: si passa alla nuova route.
 * @param results risultati delle sezioni
 */
async function save(results: Record<string, unknown>): Promise<void> {
  if (!zone.value || !form.value) return
  const body = form.value.collect(results)
  saveError.value = validateRanges(body) ?? ''
  if (saveError.value) return
  saving.value = true
  try {
    const saved = await updateZone(zone.value.id, body)
    formRef.value?.commit()
    $q.notify({ type: 'positive', message: t('zones.saved') })
    if (saved.id !== zoneId.value) await router.replace({ path: `/zones/${saved.id}`, query: route.query })
    else await load()
  } catch (error) {
    saveError.value = await describeError(error)
  } finally {
    saving.value = false
  }
}

watch(tab, (value) => void router.replace({ query: { ...route.query, tab: value === 'resets' ? 'resets' : undefined } }))
// stessa pagina con altro id (cambio zona o rinomina dell'id): ricarica
watch(zoneId, (id) => Number.isFinite(id) && void load())

/** Le modifiche non salvate dello script si confermano anche uscendo dal dettaglio. */
async function guard(): Promise<boolean> {
  if (formRef.value?.hasChanges() && !(await confirmDiscard())) return false
  return (await resets.value?.confirmLeave()) ?? true
}

/** Conferma l'uscita con i dati della zona modificati e non salvati. */
function confirmDiscard(): Promise<boolean> {
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
onBeforeRouteLeave(guard)
onBeforeRouteUpdate((to, from) => (to.params.id === from.params.id ? true : guard()))

onMounted(load)
// le capability del mondo possono arrivare dopo il montaggio: lo stato del canale si legge appena `supportsLive` e' noto
watch(canInstances, (on) => on && void loadInstances(), { immediate: true })
watch(live.enabled, (on) => on && void refreshLiveStatus(), { immediate: true })
</script>
