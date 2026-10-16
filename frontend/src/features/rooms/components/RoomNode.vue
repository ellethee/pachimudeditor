<template>
  <div class="pachi-room-node" :style="{ '--pachi-room-sector': color }">
    <div class="pachi-room-node__band">
      <span>#{{ room.vnum }}</span>
    </div>
    <div class="pachi-room-node__body">
      <div class="pachi-room-node__name" :title="room.name">{{ room.name }}</div>
      <div v-if="room.danglingExits > 0" class="pachi-room-node__badge">
        {{ t('rooms.map.dangling', { count: room.danglingExits }) }}
      </div>
    </div>

    <template v-for="direction in DIRECTIONS" :key="direction">
      <Handle
        :id="`out-${direction}`"
        type="source"
        :position="handlePosition[direction]"
        :style="handleStyle(direction, 'out')"
        class="pachi-room-node__handle pachi-room-node__handle--out"
      />
      <Handle
        :id="`in-${direction}`"
        type="target"
        :position="handlePosition[direction]"
        :style="handleStyle(direction, 'in')"
        class="pachi-room-node__handle pachi-room-node__handle--in"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * Nodo "stanza" della mappa: fascia colorata col terreno, vnum, nome, avviso per le
 * uscite senza destinazione. Due handle per direzione (uscita `out-<dir>`, ingresso
 * `in-<dir>`) sul lato della bussola corrispondente, così gli archi si attaccano dal
 * lato giusto; Su/Giù condividono il lato di Est/Ovest, spostati per non sovrapporsi.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Handle, Position } from '@vue-flow/core'
import type { NodeProps } from '@vue-flow/core'
import { DIRECTIONS, type DirectionValue } from '../utils/compass'
import type { RoomNodeData } from '../utils/graph-mapper'
import { sectorColor } from '../utils/sector-style'

const props = defineProps<NodeProps<RoomNodeData>>()
const { t } = useI18n()

const room = computed(() => props.data.room)
const color = computed(() => sectorColor(room.value.sectorType))

const handlePosition: Record<DirectionValue, Position> = {
  0: Position.Top, // NORTH
  2: Position.Bottom, // SOUTH
  1: Position.Right, // EAST
  3: Position.Left, // WEST
  4: Position.Right, // UP
  5: Position.Left, // DOWN
}

/**
 * Posizione dell'handle lungo il lato, in base a direzione e tipo.
 *
 * @param direction - direzione della bussola
 * @param kind - handle di ingresso o di uscita
 */
function handleStyle(direction: DirectionValue, kind: 'in' | 'out'): Record<string, string> {
  const offset = kind === 'out' ? '35%' : '65%'
  if (direction === 0 || direction === 2) return { left: offset }
  if (direction === 4) return { top: kind === 'out' ? '12%' : '24%' }
  if (direction === 5) return { top: kind === 'out' ? '76%' : '88%' }
  return { top: offset }
}
</script>

<style lang="scss">
.pachi-room-node {
  width: 170px;
  border: 2px solid var(--pachi-room-sector);
  border-radius: 8px;
  background: #ffffff;
  color: #263238;
  font-size: 12px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.18);
}

.pachi-room-node__band {
  padding: 2px 8px;
  border-radius: 5px 5px 0 0;
  background: var(--pachi-room-sector);
  color: #ffffff;
  font-size: 10px;
  font-weight: 600;
}

.pachi-room-node__body {
  padding: 6px 8px 8px;
}

.pachi-room-node__name {
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pachi-room-node__badge {
  margin-top: 4px;
  color: #e65100;
  font-size: 10px;
  font-weight: 600;
}

.pachi-room-node__handle {
  width: 9px;
  height: 9px;
  border: 1px solid #ffffff;
  background: #546e7a;
}

.pachi-room-node__handle--in {
  background: #90a4ae;
}

.body--dark .pachi-room-node {
  background: #263238;
  color: #eceff1;
}
</style>
