<template>
  <div class="q-pa-md column q-gutter-y-md">
    <div class="row items-center q-gutter-sm">
      <q-input v-model="search" dense outlined clearable debounce="150" class="col-12 col-sm-5 col-md-4" :label="t('shops.search')" data-testid="shops-search">
        <template #prepend><q-icon :name="mdiMagnify" /></template>
      </q-input>
      <q-toggle v-model="legacyOnly" :label="t('shops.onlyLegacy')" data-testid="shops-legacy-only" />
      <q-space />
      <q-btn
        v-if="canValidate"
        outline
        no-caps
        color="primary"
        :icon="mdiClipboardCheckOutline"
        :label="t('content.live.validate')"
        :loading="busy"
        data-testid="shops-validate"
        @click="validate"
      />
      <q-btn flat no-caps :icon="mdiRefresh" :label="t('content.reload')" :loading="loading" data-testid="shops-refresh" @click="load" />
    </div>
    <q-banner v-if="error" rounded class="bg-negative text-white" data-testid="shops-error">{{ error }}</q-banner>
    <content-problems-panel />

    <q-table
      flat
      bordered
      dense
      row-key="vnum"
      :rows="rows"
      :columns="columns"
      :loading="loading"
      :pagination="{ rowsPerPage: 50 }"
      :no-data-label="t('shops.empty')"
      data-testid="shops-table"
    >
      <template #body="p">
        <q-tr :props="p" class="cursor-pointer" data-testid="shop-row" @click="open(p.row)">
          <q-td key="vnum" :props="p">{{ p.row.vnum }}</q-td>
          <q-td key="name" :props="p">
            {{ p.row.name }}
            <q-badge v-if="p.row.legacyShopId && !p.row.hasShop" color="warning" text-color="dark" class="q-ml-sm" data-testid="shop-legacy-badge">
              {{ t('shops.legacyBadge', { id: p.row.legacyShopId }) }}
              <q-tooltip>{{ t('shops.legacy', { id: p.row.legacyShopId }) }}</q-tooltip>
            </q-badge>
          </q-td>
          <q-td key="zone" :props="p">{{ p.row.zoneName }}</q-td>
          <q-td key="produces" :props="p">
            <span v-for="(good, i) in p.row.produces" :key="good.vnum" :class="good.name === null ? 'text-negative' : ''">
              {{ i ? ', ' : '' }}#{{ good.vnum }} {{ good.name ?? t('shops.missingObject') }}
            </span>
          </q-td>
          <q-td key="trades" :props="p">{{ p.row.trades.join(', ') }}</q-td>
          <q-td key="profit" :props="p">{{ p.row.hasShop ? `${pct(p.row.profitBuy)}% / ${pct(p.row.profitSell)}%` : '' }}</q-td>
          <q-td key="hours" :props="p">{{ p.row.hasShop ? hours(p.row) : '' }}</q-td>
          <q-td key="room" :props="p">{{ p.row.room === null ? (p.row.hasShop ? t('shops.anywhere') : '') : `#${p.row.room} ${p.row.roomName ?? ''}` }}</q-td>
          <q-td key="actions" :props="p" auto-width>
            <q-btn
              v-if="canReload"
              flat
              round
              dense
              :icon="mdiReload"
              :aria-label="t('shops.reloadZone')"
              data-testid="shop-reload-zone"
              @click.stop="reloadZone(p.row)"
            >
              <q-tooltip>{{ t('shops.reloadZone') }}</q-tooltip>
            </q-btn>
          </q-td>
        </q-tr>
      </template>
    </q-table>
  </div>
</template>

<script setup lang="ts">
/**
 * Elenco di tutti i negozi del gioco (i mob con il campo `shop:`) con ricerca. Un clic apre il mob, dove si modifica la scheda del
 * negoziante; da qui si controllano i file (`content.validate`) e si rilegge una zona nel gioco acceso (`zone.reload`). I mob con il
 * vecchio `shop_id` e senza `shop` sono segnalati: il gioco li ignora.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import { useRouter } from 'vue-router'
import { mdiClipboardCheckOutline, mdiMagnify, mdiRefresh, mdiReload } from '@quasar/extras/mdi-v7'
import ContentProblemsPanel from '../../content/components/ContentProblemsPanel.vue'
import { useContentLive } from '../../content/composables/use-content-live'
import { describeError } from '../../content/helpers/describe-error'
import { useLive } from '../../playerfiles/helpers/live-state'
import { useWorld } from '../../shared/helpers/world-state'
import { listShops } from '../services/shops-api'
import type { IShopItem } from '../types/shops'

const { t } = useI18n()
const $q = useQuasar()
const router = useRouter()
const live = useLive()
const { capabilities } = useWorld()
const { busy, canValidate, validate, reloadZone: reloadZoneLive, refreshStatus } = useContentLive()

const shops = ref<IShopItem[]>([])
const loading = ref(false)
const error = ref('')
const search = ref('')
const legacyOnly = ref(false)

/** «Ricarica zona»: canale live connesso, scrittura consentita e comando `zone.reload` dichiarato dal gioco. */
const canReload = computed(() => live.canWrite.value && (live.status.value?.commands ?? []).includes('zone.reload'))

/** Righe filtrate per ricerca (mob, zona, merci, tipi comprati, stanza) e, se richiesto, per il solo `shop_id` legacy. */
const rows = computed(() => {
  const needle = (search.value ?? '').trim().toLowerCase()
  return shops.value.filter((s) => {
    if (legacyOnly.value && (s.hasShop || !s.legacyShopId)) return false
    if (!needle) return true
    const hay = [s.vnum, s.name, s.zoneName, s.roomName ?? '', s.room ?? '', s.legacyShopId ?? '', s.handler ?? '', ...s.trades, ...s.produces.map((g) => `${g.vnum} ${g.name ?? ''}`)]
    return hay.join(' ').toLowerCase().includes(needle)
  })
})

const columns = computed(() =>
  (['vnum', 'name', 'zone', 'produces', 'trades', 'profit', 'hours', 'room', 'actions'] as const).map((name) => ({
    name,
    label: name === 'actions' ? '' : t(`shops.columns.${name}`),
    field: name,
    align: 'left' as const,
  })),
)

/** Percentuale di un moltiplicatore. */
function pct(value: number): number {
  return Math.round(value * 100)
}

/** Orari di apertura (`28` = sempre aperto). */
function hours(s: IShopItem): string {
  const first = s.close1 >= 28 ? t('shops.always') : `${s.open1}–${s.close1}`
  return s.open2 || s.close2 ? `${first}, ${s.open2}–${s.close2}` : first
}

/** Apre il mob (nel gioco `id == vnum`). */
function open(row: IShopItem): void {
  void router.push(`/mobs/${row.vnum}`)
}

/** Carica l'elenco. */
async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    shops.value = await listShops()
  } catch (e) {
    error.value = await describeError(e)
  } finally {
    loading.value = false
  }
}

/** Chiede al gioco acceso di rileggere dai file la zona del negozio. */
async function reloadZone(row: IShopItem): Promise<void> {
  await reloadZoneLive(row.zoneId)
}

onMounted(async () => {
  void load()
  if (!capabilities.value?.supportsLive) return // senza canale live niente richieste (il mondo risponde 409)
  await refreshStatus()
  void validate()
})
</script>
