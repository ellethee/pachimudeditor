<template>
  <q-page padding data-testid="no-worlds">
    <div class="text-h6">{{ t('worlds.none.title') }}</div>
    <p class="q-mt-md">{{ t('worlds.none.body') }}</p>
    <pre class="q-pa-md bg-grey-2 text-dark rounded-borders">{{ example }}</pre>
    <p>{{ t('worlds.none.after') }}</p>
  </q-page>
</template>

<script setup lang="ts">
/** Istruzioni per configurare il primo mondo quando `GET /api/worlds` è vuoto. */
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const example = `webeditor_worlds:
  - { id: basedmud, kind: basedmud, name: BasedMud, path: /percorso/basedmud/area }
  - { id: dikumod, kind: dikumod, name: Diku Modificato, path: /percorso/dikumod2/lib }
  - { id: tba, kind: mapping, mapping: /percorso/tba.mapping.yaml, path: /percorso/tba/lib }
  - { id: pachimud, kind: pachimud, config_path: /percorso/pachimud.yaml }`
</script>
