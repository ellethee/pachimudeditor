<template>
  <div v-if="activeWorld" class="row items-center no-wrap q-mr-sm" data-testid="world-selector">
    <q-select
      v-if="worlds.length > 1"
      :model-value="activeWorld.id"
      :options="options"
      option-value="id"
      option-label="name"
      emit-value
      map-options
      dense
      outlined
      options-dense
      hide-bottom-space
      :aria-label="t('worlds.selector')"
      class="pachi-world-select"
      data-testid="world-select"
      @update:model-value="change"
    >
      <template #prepend>
        <q-icon :name="mdiEarth" size="xs" />
      </template>
    </q-select>
    <q-badge
      v-if="readOnly"
      color="warning"
      text-color="dark"
      class="q-ml-sm"
      :label="t('worlds.readOnly')"
      data-testid="world-readonly"
    >
      <q-tooltip>{{ t('worlds.readOnlyHint') }}</q-tooltip>
    </q-badge>
  </div>
</template>

<script setup lang="ts">
/**
 * Selettore del mondo nella barra dell'app: compare solo con più di un mondo configurato e mostra un badge
 * "sola lettura" se il mondo attivo non è scrivibile. Cambiare mondo riporta alla dashboard e ricarica la
 * pagina: tutti gli store, i filtri e le cache dell'editor ripartono dal mondo nuovo.
 */
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { mdiEarth } from '@quasar/extras/mdi-v7'
import { ensureWorlds, selectWorld, useWorld } from '../helpers/world-state'

const { t } = useI18n()
const router = useRouter()
const { worlds, loaded, activeWorld, readOnly } = useWorld()

const options = computed(() => worlds.value.map((world) => ({ id: world.id, name: world.name })))

/**
 * Applica il mondo scelto.
 *
 * @param id - id del mondo
 */
async function change(id: string): Promise<void> {
  if (id === activeWorld.value?.id) return
  selectWorld(id)
  await router.replace('/')
  window.location.reload()
}

onMounted(async () => {
  await ensureWorlds()
  // nessun mondo configurato: pagina con le istruzioni
  if (loaded.value && worlds.value.length === 0 && router.currentRoute.value.path !== '/no-worlds') {
    await router.replace('/no-worlds')
  }
})
</script>

<style lang="scss">
.pachi-world-select {
  min-width: 170px;
}
</style>
