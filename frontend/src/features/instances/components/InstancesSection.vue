<template>
  <instances-tab :kind="kind" :prototype-id="prototypeId" />
</template>

<script setup lang="ts">
/**
 * Sezione di `PachiEditDialog` che incorpora `InstancesTab`: le istanze vive del prototipo che si sta
 * modificando. Non ha stato proprio (le istanze si gestiscono dentro la tabella, con richieste dirette):
 * espone solo il contratto minimo delle sezioni, senza modifiche in sospeso.
 */
import InstancesTab from './InstancesTab.vue'
import type { InstanceKind } from '../types/instances'

defineProps<{
  /** Mob o oggetti. */
  kind: InstanceKind
  /** Id del prototipo. */
  prototypeId: number
  /** Richiesto dal contratto delle sezioni; non usato. */
  initialValue?: unknown
}>()

defineExpose({
  reset: () => undefined,
  commit: () => undefined,
  getResults: () => ({}),
  hasChanges: () => false,
})
</script>
