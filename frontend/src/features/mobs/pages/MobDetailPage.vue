<template>
  <div class="q-pa-md">
    <div class="row items-center q-mb-md q-gutter-md">
      <q-btn flat round :icon="mdiArrowLeft" :to="backTo" :aria-label="t('mobs.detail.back')">
        <q-tooltip>{{ t('mobs.detail.back') }}</q-tooltip>
      </q-btn>
      <h1 class="text-h5 q-my-none">{{ mob ? `#${mob.vnum} — ${mob.shortDescription}` : t('mobs.detail.title') }}</h1>
      <q-space />
      <q-btn v-if="mob && !readOnly && !guardOf(mob.extra).corrupted" outline color="negative" no-caps :icon="mdiDelete" :label="t('mobs.detail.remove')" @click="remove" />
    </div>

    <q-banner v-if="failed" rounded class="bg-negative text-white" data-testid="mob-not-found">{{ t('mobs.detail.notFound') }}</q-banner>

    <div v-else-if="mob && form" class="row q-col-gutter-lg">
      <div class="col-12 col-lg-8">
        <style-hints kind="mob" :record="mob" />
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
          <q-card-section class="text-h6">{{ t('mobs.detail.references') }}</q-card-section>
          <q-separator />
          <q-list dense>
            <q-item-label header>{{ t('mobs.detail.resets', { count: usage.length }) }}</q-item-label>
            <q-item v-for="use in usage" :key="use.resetCommandId" clickable :to="{ path: `/zones/${use.zoneId}`, query: { tab: 'resets' } }">
              <q-item-section>
                <q-item-label>{{ use.zoneName }}</q-item-label>
                <q-item-label caption>#{{ use.orderIndex + 1 }}</q-item-label>
              </q-item-section>
            </q-item>
            <q-item v-if="usage.length === 0"><q-item-section class="text-grey">{{ t('mobs.detail.none') }}</q-item-section></q-item>
          </q-list>
        </q-card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * Dettaglio mob: maschera di modifica inline (le stesse sezioni del dialogo di creazione) e pannello dei riferimenti
 * (comandi di reset che lo caricano).
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { mdiArrowLeft, mdiDelete } from '@quasar/extras/mdi-v7'
import { loadMobLookups, useMobForm } from '../composables/use-mob-form'
import type { IMobLookups } from '../composables/use-mob-form'
import { describeError } from '../helpers/describe-error'
import { deleteMob, getMob, getMobUsage, updateMob } from '../services/mobs-api'
import type { IMobs, IResetUsage } from '../types/mobs'
import SectionsForm from '../../shared/components/SectionsForm.vue'
import StyleHints from '../../shared/components/StyleHints.vue'
import { guardOf } from '../../shared/helpers/record-guard'
import { useWorld } from '../../shared/helpers/world-state'

const { t } = useI18n()
const $q = useQuasar()
const route = useRoute()
const router = useRouter()
const { readOnly } = useWorld()
const { prepareMobForm } = useMobForm()

const mobId = computed(() => Number(route.params.id))
const mob = ref<IMobs | null>(null)
const failed = ref(false)
const usage = ref<IResetUsage[]>([])
const form = ref<Awaited<ReturnType<typeof prepareMobForm>> | null>(null)
const formKey = ref(0)
const formRef = ref<{ commit: () => void; hasChanges: () => boolean } | null>(null)
const saving = ref(false)
const saveError = ref('')
let lookups: IMobLookups | null = null

const backTo = computed(() => ({ path: '/mobs', query: mob.value ? { zoneId: String(mob.value.zoneId) } : {} }))

/** Carica mob, riferimenti e form (nuova `key` = rimonta le sezioni con la nuova base). */
async function load(): Promise<void> {
  failed.value = false
  try {
    lookups ??= await loadMobLookups()
    mob.value = await getMob(mobId.value)
  } catch {
    mob.value = null
    form.value = null
    failed.value = true
    return
  }
  form.value = await prepareMobForm(lookups, mob.value)
  formKey.value++
  usage.value = await getMobUsage(mobId.value).catch(() => [])
}

/**
 * Salva il mob (PUT = patch parziale: vnum e zona non si cambiano).
 * @param results risultati delle sezioni
 */
async function save(results: Record<string, unknown>): Promise<void> {
  if (!form.value) return
  const { vnum: _vnum, ...patch } = form.value.collect(results)
  saving.value = true
  saveError.value = ''
  try {
    await updateMob(mobId.value, patch)
    formRef.value?.commit()
    $q.notify({ type: 'positive', message: t('mobs.detail.saved') })
    await load()
  } catch (error) {
    saveError.value = await describeError(error)
  } finally {
    saving.value = false
  }
}

/** Elimina il mob dopo conferma, con avviso se è usato dai reset. */
function remove(): void {
  if (!mob.value) return
  const { shortDescription, vnum, zoneId } = mob.value
  const zones = [...new Set(usage.value.map((u) => u.zoneName))].join(', ')
  const warning = usage.value.length > 0 ? ' ' + t('mobs.delete.usageWarning', { count: usage.value.length, zones }) : ''
  $q.dialog({ title: t('mobs.delete.title'), message: t('mobs.delete.message', { name: shortDescription, vnum }) + warning, cancel: true, persistent: true }).onOk(async () => {
    try {
      await deleteMob(mobId.value)
      formRef.value?.commit()
      await router.push({ path: '/mobs', query: { zoneId: String(zoneId) } })
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
watch(mobId, (id) => Number.isFinite(id) && void load())
onMounted(load)
</script>
