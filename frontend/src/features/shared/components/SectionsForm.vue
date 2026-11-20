<template>
  <div class="column q-gutter-md">
    <q-banner v-if="error" rounded class="bg-negative text-white" data-testid="form-error">{{ error }}</q-banner>
    <sections-container ref="container" :sections="sections" :common-props="readonly ? { readonly: true } : {}" />
    <q-banner v-if="error && !readonly" dense rounded class="bg-negative text-white" data-testid="form-error-bottom">{{ error }}</q-banner>
    <div v-if="!readonly" class="row items-center q-gutter-sm">
      <q-btn
        color="primary"
        no-caps
        :icon="mdiContentSave"
        :label="t('forms.save')"
        :loading="saving"
        :disable="!dirty"
        data-testid="form-save"
        @click="save"
      />
      <q-btn flat no-caps :label="t('forms.revert')" :disable="!dirty || saving" data-testid="form-revert" @click="revert" />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * Maschera di modifica inline: stesse sezioni (`ISectionDefinition`) dei dialoghi di `PachiEditDialog`, ma in pagina
 * con Salva / Annulla modifiche. Il padre salva in `@save` e chiama `commit()` a salvataggio riuscito.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { mdiContentSave } from '@quasar/extras/mdi-v7'
import { SectionsContainer } from '@ilpachi/pachi-kit/edit-dialog'
import type { ISectionDefinition, SectionsContainerExpose } from '@ilpachi/pachi-kit/edit-dialog'

defineProps<{
  sections: ISectionDefinition[]
  readonly?: boolean
  saving?: boolean
  /** Messaggio d'errore dell'ultimo salvataggio. */
  error?: string
}>()
const emit = defineEmits<{ save: [results: Record<string, unknown>] }>()

const { t } = useI18n()
const container = ref<SectionsContainerExpose | null>(null)
const dirty = computed(() => container.value?.hasChanges() ?? false)

/** Valida le sezioni e, se valide, emette i risultati. */
async function save(): Promise<void> {
  if (!container.value || !(await container.value.validateAll())) return
  emit('save', await container.value.getResults())
}

/** Torna ai valori salvati. */
function revert(): Promise<void> | undefined {
  return container.value?.resetAll()
}

/** Da chiamare a salvataggio riuscito: i valori correnti diventano la base. */
function commit(): void {
  container.value?.commitAll()
}

defineExpose({ commit, hasChanges: () => dirty.value })
</script>
