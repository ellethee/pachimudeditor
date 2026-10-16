<template>
  <div>
    <q-linear-progress v-if="loading" indeterminate />
    <q-banner v-else-if="failed" class="bg-negative text-white" rounded dense>
      {{ t('instances.loadError') }}
    </q-banner>
    <instances-table v-else-if="prototype" :kind="kind" :prototype="prototype" />
  </div>
</template>

<script setup lang="ts">
/**
 * Tab riusabile con le istanze vive di un prototipo, da incorporare nei dialog di mob/oggetti.
 *
 * Esempio: `<instances-tab kind="mob" :prototype-id="mob.id" />`. Carica il prototipo (per sapere
 * zona, tipo e slot) e mostra `InstancesTable` filtrata; da qui si possono generare, modificare ed
 * eliminare istanze di quel prototipo.
 */
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import InstancesTable from './InstancesTable.vue'
import { getPrototype } from '../services/instances-api'
import type { InstanceKind, IPrototypeRef } from '../types/instances'

const props = defineProps<{
  /** Mob o oggetti. */
  kind: InstanceKind
  /** Id del prototipo (`MobPrototype.id` / `ObjectPrototype.id`). */
  prototypeId: number
}>()

const { t } = useI18n()
const prototype = ref<IPrototypeRef>()
const loading = ref(true)
const failed = ref(false)

/** Carica il prototipo corrente. */
async function load(): Promise<void> {
  loading.value = true
  failed.value = false
  try {
    prototype.value = await getPrototype(props.kind, props.prototypeId)
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => [props.kind, props.prototypeId], load)
</script>
