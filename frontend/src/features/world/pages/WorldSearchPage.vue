<template>
  <div class="q-pa-md">
    <h1 class="text-h5 q-mt-none q-mb-md">{{ t('world.search.title') }}</h1>

    <div class="row items-center q-gutter-md q-mb-md">
      <q-input
        v-model="text"
        dense
        outlined
        clearable
        autofocus
        style="min-width: 320px; flex: 1 1 320px; max-width: 520px"
        :label="t('world.search.label')"
        @keyup.enter="submit"
      >
        <template #prepend><q-icon :name="mdiMagnify" /></template>
      </q-input>
      <q-option-group
        v-model="selectedTypes"
        type="checkbox"
        inline
        dense
        :options="typeOptions"
      />
      <q-btn color="primary" unelevated :label="t('world.search.submit')" :loading="loading" @click="submit" />
    </div>

    <pachi-error-state
      v-if="loadError"
      :title="t('world.errorTitle')"
      :description="t('world.errorDescription')"
      :primary-label="t('world.retry')"
      @primary="run"
    />
    <div v-else-if="!results" class="text-grey">{{ t('world.search.minChars') }}</div>
    <div v-else-if="groups.every((g) => g.group.items.length === 0)" class="text-grey">
      {{ t('world.search.noResults') }}
    </div>

    <template v-else>
      <q-card v-for="g in groups.filter((x) => x.group.items.length > 0)" :key="g.type" flat bordered class="q-mb-md">
        <q-card-section class="row items-center">
          <div class="text-h6">{{ t(`world.type.${g.type}`) }}</div>
          <q-space />
          <div class="text-caption text-grey">
            {{ t('world.search.total', { shown: g.group.items.length, total: g.group.total }) }}
          </div>
        </q-card-section>
        <q-list separator>
          <q-item v-for="hit in g.group.items" :key="hit.id" clickable :to="entityLocation(g.type, hit.id, hit.zoneId)">
            <q-item-section avatar>
              <q-badge outline color="primary">{{ hit.vnum }}</q-badge>
            </q-item-section>
            <q-item-section>
              <q-item-label>{{ hit.name }}</q-item-label>
              <q-item-label caption>
                <template v-if="hit.keywords">{{ hit.keywords }} · </template>
                <template v-if="g.type !== 'zone'">{{ t('world.search.inZone', { zone: hit.zoneName }) }}</template>
              </q-item-label>
            </q-item-section>
            <q-item-section side><q-icon :name="mdiOpenInNew" /></q-item-section>
          </q-item>
        </q-list>
      </q-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { mdiMagnify, mdiOpenInNew } from '@quasar/extras/mdi-v7'
import { searchWorld } from '../services/world-api'
import type { ISearchGroup, ISearchResults, WorldEntityType } from '../types/world'
import { entityLocation } from '../utils/entity-links'

/**
 * Ricerca globale su zone, stanze, mob e oggetti (vnum o nome/keywords). Il testo sta nella query
 * string (`/world/search?q=`), così la ricerca è condivisibile e usabile dalla panoramica.
 */
const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const ALL_TYPES: WorldEntityType[] = ['zone', 'room', 'mob', 'object']
const text = ref<string | null>(typeof route.query.q === 'string' ? route.query.q : '')
const selectedTypes = ref<WorldEntityType[]>([...ALL_TYPES])
const results = ref<ISearchResults | null>(null)
const loading = ref(false)
const loadError = ref(false)

const typeOptions = computed(() => ALL_TYPES.map((type) => ({ value: type, label: t(`world.type.${type}`) })))

/** Gruppi di risultati nell'ordine zone, stanze, mob, oggetti. */
const groups = computed<{ type: WorldEntityType; group: ISearchGroup }[]>(() => {
  const r = results.value
  if (!r) return []
  return [
    { type: 'zone', group: r.zones },
    { type: 'room', group: r.rooms },
    { type: 'mob', group: r.mobs },
    { type: 'object', group: r.objects },
  ]
})

/** Esegue la ricerca sul testo corrente (se non vuoto). */
async function run(): Promise<void> {
  const q = (text.value ?? '').trim()
  if (!q || selectedTypes.value.length === 0) {
    results.value = null
    return
  }
  loading.value = true
  loadError.value = false
  try {
    results.value = await searchWorld(q, selectedTypes.value.length === ALL_TYPES.length ? [] : selectedTypes.value)
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

/** Aggiorna la query string e cerca. */
function submit(): void {
  const q = (text.value ?? '').trim()
  if (q === route.query.q) void run()
  else void router.replace({ path: '/world/search', query: q ? { q } : {} })
}

watch(
  () => route.query.q,
  (q) => {
    text.value = typeof q === 'string' ? q : ''
    void run()
  },
)

onMounted(run)
</script>
