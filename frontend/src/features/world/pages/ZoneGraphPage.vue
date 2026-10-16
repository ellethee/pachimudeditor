<template>
  <div class="column no-wrap q-px-md q-pt-md" style="height: var(--pachi-page-height, 70vh)">
    <div class="row items-center q-gutter-md q-pb-sm" style="flex: 0 0 auto">
      <h1 class="text-h5 q-ma-none">{{ t('world.graph.title') }}</h1>
      <q-btn flat dense :icon="mdiFitToScreen" :label="t('world.graph.fit')" @click="fitAll" />
      <q-btn flat dense :icon="mdiRefresh" :label="t('world.reload')" :loading="loading" @click="load" />
      <q-space />
      <div class="text-caption text-grey">{{ t('world.graph.hint') }}</div>
    </div>

    <pachi-error-state
      v-if="loadError"
      :title="t('world.errorTitle')"
      :description="t('world.errorDescription')"
      :primary-label="t('world.retry')"
      @primary="load"
    />

    <div v-else class="row no-wrap" style="flex: 1 1 auto; min-height: 0">
      <div class="relative-position" style="flex: 1 1 auto; min-width: 0">
        <VueFlow
          v-if="!loading"
          :nodes="nodes"
          :edges="edges"
          :min-zoom="0.1"
          :max-zoom="2"
          :default-viewport="{ zoom: 0.8 }"
          @nodes-initialized="fitAll"
          @node-click="onNodeClick"
        >
          <Background :gap="24" pattern-color="#b0bec5" />
          <Controls position="bottom-left" />
          <MiniMap pannable zoomable />
        </VueFlow>
        <div v-if="!loading && nodes.length === 0" class="absolute-center text-grey-7">
          {{ t('world.graph.empty') }}
        </div>
      </div>

      <q-card flat bordered class="q-ml-md" style="flex: 0 0 260px; overflow: auto">
        <q-card-section class="text-subtitle1">{{ t('world.graph.isolated') }}</q-card-section>
        <q-list v-if="isolated.length > 0" dense>
          <q-item v-for="zone in isolated" :key="zone.id" clickable :to="entityLocation('zone', zone.id, zone.id)">
            <q-item-section avatar>
              <q-badge outline color="warning">{{ zone.vnum }}</q-badge>
            </q-item-section>
            <q-item-section>{{ zone.name }}</q-item-section>
          </q-item>
        </q-list>
        <q-card-section v-else class="text-grey">{{ t('world.graph.noneIsolated') }}</q-card-section>
      </q-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

import { computed, nextTick, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { mdiFitToScreen, mdiRefresh } from '@quasar/extras/mdi-v7'
import { MarkerType, VueFlow, useVueFlow } from '@vue-flow/core'
import type { Edge, Node, NodeMouseEvent } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import { getZoneGraph } from '../services/world-api'
import type { IZoneGraph, IZoneGraphNode } from '../types/world'
import { entityLocation } from '../utils/entity-links'
import { circleLayout } from '../utils/zone-layout'

/**
 * Grafo delle zone (vue-flow): un nodo per zona, un arco orientato per ogni coppia di zone collegata da
 * uscite, etichettato col numero di uscite. Le zone isolate sono evidenziate e riepilogate a lato.
 * Un clic su una zona apre l'elenco delle sue stanze.
 */
const { t } = useI18n()
const router = useRouter()
const { fitView } = useVueFlow()

const graph = ref<IZoneGraph | null>(null)
const nodes = ref<Node[]>([])
const edges = ref<Edge[]>([])
const loading = ref(false)
const loadError = ref(false)

const isolated = computed<IZoneGraphNode[]>(() => graph.value?.nodes.filter((n) => n.isolated) ?? [])

/** Stile di un nodo zona: bordo arancio se isolata, grigio tratteggiato se disattivata. */
function nodeStyle(zone: IZoneGraphNode): Record<string, string> {
  return {
    width: '180px',
    padding: '8px',
    borderRadius: '6px',
    textAlign: 'center',
    border: `2px ${zone.enabled ? 'solid' : 'dashed'} ${zone.isolated ? '#ef6c00' : '#546e7a'}`,
    opacity: zone.enabled ? '1' : '0.6',
  }
}

/** Costruisce nodi (su cerchio) e archi vue-flow dal grafo del backend. */
function toFlow(data: IZoneGraph): void {
  const points = circleLayout(data.nodes.length)
  nodes.value = data.nodes.map((zone, i) => ({
    id: String(zone.id),
    position: points[i] ?? { x: 0, y: 0 },
    label: `#${zone.vnum} ${zone.name}\n${t('world.graph.nodeRooms', { count: zone.rooms })}`,
    style: nodeStyle(zone),
  }))
  edges.value = data.edges.map((edge) => ({
    id: `z${edge.fromZoneId}-${edge.toZoneId}`,
    source: String(edge.fromZoneId),
    target: String(edge.toZoneId),
    label: t('world.graph.edgeLabel', { count: edge.count }),
    markerEnd: MarkerType.ArrowClosed,
    style: { strokeWidth: Math.min(1 + edge.count, 6) },
  }))
}

/** Carica il grafo. */
async function load(): Promise<void> {
  loading.value = true
  loadError.value = false
  try {
    graph.value = await getZoneGraph()
    toFlow(graph.value)
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
  await nextTick()
  fitAll()
}

/** Adatta la vista a tutto il grafo. */
function fitAll(): void {
  void fitView({ padding: 0.2 })
}

/** Clic su una zona: apre le sue stanze nell'editor. */
function onNodeClick(event: NodeMouseEvent): void {
  void router.push({ path: '/rooms', query: { zoneId: event.node.id } })
}

onMounted(load)
</script>
