<template>
  <div class="q-pa-md">
    <div class="row items-center q-mb-md q-gutter-md">
      <q-btn flat round :icon="mdiArrowLeft" :to="backTo" :aria-label="t('rooms.detail.back')">
        <q-tooltip>{{ t('rooms.detail.back') }}</q-tooltip>
      </q-btn>
      <h1 class="text-h5 q-my-none">{{ room ? `#${room.vnum} — ${room.name}` : t('rooms.detail.title') }}</h1>
      <q-space />
      <q-btn v-if="room" outline color="teal" no-caps :icon="mdiGraphOutline" :label="t('rooms.detail.viewMap')" :to="mapTo" />
      <q-btn v-if="room && !readOnly" outline color="negative" no-caps :icon="mdiDelete" :label="t('rooms.detail.remove')" @click="remove" />
    </div>

    <q-banner v-if="failed" rounded class="bg-negative text-white" data-testid="room-not-found">
      {{ t('rooms.detail.notFound') }}
    </q-banner>

    <div v-else-if="room && editor" class="row q-col-gutter-lg">
      <div class="col-12 col-lg-8">
        <style-hints kind="room" :record="room" />
        <sections-form
          :key="formKey"
          ref="formRef"
          :sections="editor.sections"
          :readonly="editor.locked"
          :saving="saving"
          :error="saveError"
          @save="save"
        />
      </div>

      <div class="col-12 col-lg-4">
        <collapsible-card :title="t('rooms.detail.references')" storage-key="room-references" testid="room-references">
          <q-list separator>
            <q-expansion-item default-opened :icon="mdiLogin" :label="t('rooms.detail.incoming', { count: incoming.length })">
              <q-list dense>
                <q-item v-for="exit in incoming" :key="exit.exitId" clickable :to="`/rooms/${exit.roomId}`">
                  <q-item-section>
                    <q-item-label>#{{ exit.roomVnum }} — {{ exit.roomName }}</q-item-label>
                    <q-item-label caption>{{ directionLabel(exit.direction) }}</q-item-label>
                  </q-item-section>
                </q-item>
                <q-item v-if="incoming.length === 0"><q-item-section class="text-grey">{{ t('rooms.detail.none') }}</q-item-section></q-item>
              </q-list>
            </q-expansion-item>
            <q-expansion-item default-opened :icon="mdiReplay" :label="t('rooms.detail.resets', { count: usage.length })">
              <q-list dense>
                <q-item v-for="use in usage" :key="use.resetCommandId" clickable :to="{ path: `/zones/${use.zoneId}`, query: { tab: 'resets' } }">
                  <q-item-section>
                    <q-item-label>{{ use.zoneName }}</q-item-label>
                    <q-item-label caption>#{{ use.orderIndex + 1 }}</q-item-label>
                  </q-item-section>
                </q-item>
                <q-item v-if="usage.length === 0"><q-item-section class="text-grey">{{ t('rooms.detail.none') }}</q-item-section></q-item>
              </q-list>
            </q-expansion-item>
          </q-list>
        </collapsible-card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * Dettaglio stanza: maschera di modifica inline (dati, uscite, extra description e campi del mondo, le stesse sezioni
 * del dialogo di creazione) e pannello dei riferimenti (uscite in entrata, comandi di reset che la usano).
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { mdiArrowLeft, mdiDelete, mdiGraphOutline, mdiLogin, mdiReplay } from '@quasar/extras/mdi-v7'
import { useRoomDialogs } from '../composables/use-room-dialogs'
import { deleteRoom, getIncomingExits, getRoomUsage } from '../services/rooms-api'
import { useRoomsStore } from '../stores/use-rooms-store'
import { describeError } from '../utils/error-helper'
import type { IIncomingExit, IResetUsage, IRoomDetail } from '../types/rooms'
import SectionsForm from '../../shared/components/SectionsForm.vue'
import CollapsibleCard from '../../shared/components/CollapsibleCard.vue'
import StyleHints from '../../shared/components/StyleHints.vue'
import { useWorld } from '../../shared/helpers/world-state'

const { t, te } = useI18n()
const $q = useQuasar()
const route = useRoute()
const router = useRouter()
const store = useRoomsStore()
const { readOnly } = useWorld()

const roomId = computed(() => Number(route.params.id))
const room = ref<IRoomDetail | null>(null)
const failed = ref(false)
const incoming = ref<IIncomingExit[]>([])
const usage = ref<IResetUsage[]>([])
const saving = ref(false)
const saveError = ref('')
const formKey = ref(0)
const formRef = ref<{ commit: () => void; hasChanges: () => boolean } | null>(null)
const editor = ref<Awaited<ReturnType<typeof dialogs.prepareEdit>> | null>(null)

const dialogs = useRoomDialogs(() => undefined)

const backTo = computed(() => ({ path: '/rooms', query: room.value ? { zoneId: String(room.value.zoneId) } : {} }))
const mapTo = computed(() => ({ path: '/rooms/map', query: room.value ? { zoneId: String(room.value.zoneId), roomId: String(room.value.id) } : {} }))

/**
 * Etichetta di una direzione.
 * @param direction valore dell'enum
 */
function directionLabel(direction: number): string {
  return store.enums?.direction.find((option) => option.value === direction)?.label ?? String(direction)
}

/** Carica stanza, riferimenti ed editor (nuova `key` = rimonta le sezioni con la nuova base). */
async function load(): Promise<void> {
  failed.value = false
  try {
    editor.value = await dialogs.prepareEdit(roomId.value)
  } catch {
    room.value = null
    editor.value = null
    failed.value = true
    return
  }
  room.value = editor.value.detail
  formKey.value++
  // i riferimenti sono accessori: un errore non blocca la maschera
  ;[incoming.value, usage.value] = await Promise.all([
    getIncomingExits(roomId.value).catch(() => []),
    getRoomUsage(roomId.value).catch(() => []),
  ])
}

/**
 * Salva la maschera e ricarica (le uscite create/eliminate cambiano gli id).
 * @param results risultati delle sezioni
 */
async function save(results: Record<string, unknown>): Promise<void> {
  if (!editor.value) return
  saving.value = true
  saveError.value = ''
  try {
    await editor.value.save(results)
    formRef.value?.commit()
    $q.notify({ type: 'positive', message: t('rooms.notify.saved') })
    await load()
  } catch (error) {
    saveError.value = await describeError(error, t, te)
  } finally {
    saving.value = false
  }
}

/** Elimina la stanza dopo conferma, con avviso se è usata dai reset. */
function remove(): void {
  if (!room.value) return
  const { name, vnum, zoneId } = room.value
  const warning =
    usage.value.length > 0
      ? ' ' + t('rooms.delete.usageWarning', { count: usage.value.length, zones: [...new Set(usage.value.map((u) => u.zoneName))].join(', ') })
      : ''
  $q.dialog({ title: t('rooms.detail.remove'), message: t('rooms.delete.message', { name, vnum }) + warning, cancel: true, persistent: true }).onOk(async () => {
    try {
      await deleteRoom(roomId.value)
      formRef.value?.commit()
      $q.notify({ type: 'positive', message: t('rooms.detail.deleted') })
      await router.push({ path: '/rooms', query: { zoneId: String(zoneId) } })
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
watch(roomId, (id) => Number.isFinite(id) && void load())
onMounted(async () => {
  await store.ensureEnums()
  await load()
})
</script>
