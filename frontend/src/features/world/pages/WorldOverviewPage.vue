<template>
  <div class="q-pa-md">
    <div class="row items-center q-mb-md q-gutter-md">
      <h1 class="text-h5 q-my-none">{{ t('world.title') }}</h1>
      <q-input
        v-model="searchText"
        dense
        outlined
        clearable
        style="min-width: 320px; flex: 1 1 320px; max-width: 520px"
        :placeholder="t('world.searchPlaceholder')"
        @keyup.enter="goSearch"
      >
        <template #prepend><q-icon :name="mdiMagnify" /></template>
      </q-input>
      <q-space />
      <q-btn flat dense :icon="mdiRefresh" :label="t('world.reload')" :loading="loading" @click="load" />
    </div>

    <pachi-error-state
      v-if="loadError"
      :title="t('world.errorTitle')"
      :description="t('world.errorDescription')"
      :primary-label="t('world.retry')"
      @primary="load"
    />

    <template v-else-if="overview">
      <div class="row q-col-gutter-md q-mb-md">
        <div v-for="card in cards" :key="card.key" class="col-6 col-sm-4 col-md-3 col-lg-2">
          <q-card flat bordered class="full-height">
            <q-card-section class="row items-center no-wrap">
              <q-icon :name="card.icon" size="32px" color="primary" class="q-mr-md" />
              <div>
                <div class="text-h5">{{ card.value }}</div>
                <div class="text-caption text-grey-7">{{ card.label }}</div>
                <div v-if="card.detail" class="text-caption text-grey">{{ card.detail }}</div>
              </div>
            </q-card-section>
          </q-card>
        </div>
      </div>

      <q-card flat bordered class="q-mb-md">
        <q-card-section class="text-h6">{{ t('world.zonesTable.title') }}</q-card-section>
        <q-markup-table flat dense separator="horizontal">
          <thead>
            <tr>
              <th class="text-left">{{ t('world.zonesTable.vnum') }}</th>
              <th class="text-left">{{ t('world.zonesTable.name') }}</th>
              <th class="text-right">{{ t('world.zonesTable.rooms') }}</th>
              <th class="text-right">{{ t('world.zonesTable.mobs') }}</th>
              <th class="text-right">{{ t('world.zonesTable.objects') }}</th>
              <th class="text-left">{{ t('world.zonesTable.range') }}</th>
              <th class="text-left" style="min-width: 160px">{{ t('world.zonesTable.usage') }}</th>
              <th class="text-right">{{ t('world.zonesTable.resets') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="zone in overview.zones" :key="zone.id">
              <td>{{ zone.vnum }}</td>
              <td>
                <router-link :to="entityLocation('zone', zone.id, zone.id)">{{ zone.name }}</router-link>
                <q-badge v-if="!zone.enabled" color="grey" class="q-ml-sm">{{ t('world.zonesTable.disabled') }}</q-badge>
              </td>
              <td class="text-right">
                <router-link :to="roomsOf(zone.id)">{{ zone.rooms }}</router-link>
              </td>
              <td class="text-right">{{ zone.mobs }}</td>
              <td class="text-right">{{ zone.objects }}</td>
              <td>
                <span v-if="zone.rangeUsagePct === null" class="text-grey">{{ t('world.zonesTable.unassigned') }}</span>
                <span v-else>{{ zone.bottomVnum }}-{{ zone.topVnum }}</span>
              </td>
              <td>
                <template v-if="zone.rangeUsagePct !== null">
                  <q-linear-progress :value="zone.rangeUsagePct / 100" size="10px" rounded color="primary" />
                  <span class="text-caption">{{ zone.rangeUsagePct }}%</span>
                </template>
              </td>
              <td class="text-right">
                <router-link :to="entityLocation('zone', zone.id, zone.id, true)">{{ zone.resetCommands }}</router-link>
              </td>
            </tr>
            <tr v-if="overview.zones.length === 0">
              <td colspan="8" class="text-grey text-center">{{ t('world.zonesTable.empty') }}</td>
            </tr>
          </tbody>
        </q-markup-table>
      </q-card>

      <q-card flat bordered>
        <q-card-section class="text-h6">{{ t('world.warnings.title') }}</q-card-section>
        <q-card-section v-if="warningGroups.length === 0" class="text-grey">
          {{ t('world.warnings.none') }}
        </q-card-section>
        <q-list v-else separator>
          <q-expansion-item
            v-for="group in warningGroups"
            :key="group.kind"
            :icon="mdiAlertOutline"
            :label="t(`world.warnings.kind.${group.kind}`)"
            :caption="group.caption"
            :header-class="'text-warning'"
          >
            <q-list dense>
              <q-item v-for="(w, i) in group.items" :key="i" clickable :to="warningLocation(w)">
                <q-item-section avatar>
                  <q-badge outline color="primary">{{ w.vnum }}</q-badge>
                </q-item-section>
                <q-item-section>
                  <q-item-label>{{ w.name }}</q-item-label>
                  <q-item-label caption>
                    {{ t(`world.type.${w.entityType}`) }} · {{ w.zoneName }}<template v-if="detail(w)"> · {{ detail(w) }}</template>
                  </q-item-label>
                </q-item-section>
                <q-item-section side><q-icon :name="mdiOpenInNew" /></q-item-section>
              </q-item>
            </q-list>
          </q-expansion-item>
        </q-list>
      </q-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'
import {
  mdiAccount,
  mdiAccountGroup,
  mdiAlertOutline,
  mdiCube,
  mdiCubeOutline,
  mdiDoor,
  mdiEarth,
  mdiMagnify,
  mdiOpenInNew,
  mdiRefresh,
  mdiSkull,
  mdiSkullOutline,
} from '@quasar/extras/mdi-v7'
import { getWorldOverview } from '../services/world-api'
import type { IQualityWarning, IWorldOverview, WarningKind } from '../types/world'
import { entityLocation } from '../utils/entity-links'

/**
 * Panoramica del mondo, landing dell'editor: schede coi conteggi, tabella riepilogativa per zona
 * e warning di qualità dei dati con link all'entità da correggere.
 */
const { t } = useI18n()
const router = useRouter()

const overview = ref<IWorldOverview | null>(null)
const loading = ref(false)
const loadError = ref(false)
const searchText = ref<string | null>('')

interface ICard {
  key: string
  label: string
  value: number
  icon: string
  detail?: string
}

/** Schede dei conteggi globali. */
const cards = computed<ICard[]>(() => {
  const c = overview.value?.counts
  if (!c) return []
  return [
    {
      key: 'zones',
      label: t('world.counts.zones'),
      value: c.zones,
      icon: mdiEarth,
      detail: t('world.counts.zonesDetail', { enabled: c.zonesEnabled, disabled: c.zonesDisabled }),
    },
    { key: 'rooms', label: t('world.counts.rooms'), value: c.rooms, icon: mdiDoor },
    { key: 'mobs', label: t('world.counts.mobs'), value: c.mobs, icon: mdiSkull },
    { key: 'objects', label: t('world.counts.objects'), value: c.objects, icon: mdiCube },
    { key: 'mobInstances', label: t('world.counts.mobInstances'), value: c.mobInstances, icon: mdiSkullOutline },
    { key: 'objectInstances', label: t('world.counts.objectInstances'), value: c.objectInstances, icon: mdiCubeOutline },
    { key: 'accounts', label: t('world.counts.accounts'), value: c.accounts, icon: mdiAccount },
    { key: 'characters', label: t('world.counts.characters'), value: c.characters, icon: mdiAccountGroup },
  ]
})

interface IWarningGroup {
  kind: WarningKind
  caption: string
  items: IQualityWarning[]
}

/** Warning raggruppati per tipo, con il totale reale (il backend ne elenca al massimo 100 per tipo). */
const warningGroups = computed<IWarningGroup[]>(() => {
  const data = overview.value
  if (!data) return []
  const groups = new Map<WarningKind, IQualityWarning[]>()
  for (const w of data.warnings) groups.set(w.kind, [...(groups.get(w.kind) ?? []), w])
  return [...groups.entries()].map(([kind, items]) => {
    const total = data.warningTotals[kind] ?? items.length
    return {
      kind,
      items,
      caption:
        total > items.length
          ? t('world.warnings.truncated', { shown: items.length, total })
          : String(total),
    }
  })
})

/** Elenco stanze della zona. */
function roomsOf(zoneId: number): RouteLocationRaw {
  return { path: '/rooms', query: { zoneId: String(zoneId) } }
}

/** Dove aprire l'entità di un warning (la zona con script vuoto apre lo script di reset). */
function warningLocation(w: IQualityWarning): RouteLocationRaw {
  return entityLocation(w.entityType, w.entityId, w.zoneId, w.kind === 'zone_empty_reset_script')
}

/** Dettaglio aggiuntivo di un warning (direzione dell'uscita, range della zona). */
function detail(w: IQualityWarning): string {
  if (w.kind === 'exit_without_target') {
    return t('world.warnings.item.exit_without_target', { direction: t(`world.dir.${w.params.direction ?? 0}`) })
  }
  if (w.kind === 'vnum_out_of_range') {
    return t('world.warnings.item.vnum_out_of_range', { bottom: w.params.bottom ?? 0, top: w.params.top ?? 0 })
  }
  return ''
}

/** Apre la pagina di ricerca col testo digitato. */
function goSearch(): void {
  const q = (searchText.value ?? '').trim()
  if (q) void router.push({ path: '/world/search', query: { q } })
}

/** Carica la panoramica. */
async function load(): Promise<void> {
  loading.value = true
  loadError.value = false
  try {
    overview.value = await getWorldOverview()
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
