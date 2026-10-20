<template>
  <div v-if="activeWorld" class="row items-center no-wrap q-mr-sm pachi-world-selector" data-testid="world-selector">
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
      v-for="[key, value] in params"
      :key="key"
      outline
      color="primary"
      class="q-ml-sm gt-sm"
      :label="`${te(`worlds.params.${key}`) ? t(`worlds.params.${key}`) : key}: ${value}`"
      :data-testid="`world-param-${key}`"
    />
    <q-badge
      v-if="readOnly"
      color="warning"
      text-color="dark"
      class="q-ml-sm"
      :aria-label="t('worlds.readOnly')"
      data-testid="world-readonly"
    >
      <q-icon :name="mdiLock" class="lt-sm" />
      <span class="gt-xs">{{ t('worlds.readOnly') }}</span>
      <q-tooltip>{{ t('worlds.readOnlyHint') }}</q-tooltip>
    </q-badge>
  </div>
</template>

<script setup lang="ts">
/**
 * Selettore del mondo nella barra dell'app: compare solo con più di un mondo configurato e mostra i parametri
 * informativi non vuoti del mondo attivo (`params`) e un badge "sola lettura" se non è scrivibile. Cambiare mondo riporta alla dashboard e ricarica la
 * pagina: tutti gli store, i filtri e le cache dell'editor ripartono dal mondo nuovo.
 */
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { mdiEarth, mdiLock } from '@quasar/extras/mdi-v7'
import { ensureWorlds, selectWorld, useWorld } from '../helpers/world-state'

const { t, te } = useI18n()
const router = useRouter()
const { worlds, loaded, activeWorld, readOnly } = useWorld()

/** Parametri informativi non vuoti del mondo attivo (es. `data_prefix`, `variant`). */
const params = computed(() =>
  Object.entries(activeWorld.value?.params ?? {}).filter(([, v]) => v !== null && v !== '' && v !== undefined),
)

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
// sotto 600px la barra e' stretta: il selettore si restringe invece di uscire dallo schermo
@media (max-width: 599px) {
  .pachi-world-selector {
    min-width: 0;
    flex: 100 1 auto;
  }
  .pachi-world-select {
    flex: 1 1 0;
    min-width: 0;
  }
}
</style>
