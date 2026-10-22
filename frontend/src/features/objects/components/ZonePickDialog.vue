<template>
  <q-dialog ref="dialogRef" @hide="onDialogHide">
    <q-card style="min-width: 320px; max-width: 95vw">
      <q-form @submit.prevent="confirm">
        <q-card-section>
          <div class="text-h6">{{ t('objects.pickZone.title') }}</div>
          <div class="text-body2 q-mt-xs">{{ t('objects.pickZone.message') }}</div>
        </q-card-section>
        <q-card-section class="q-pt-none">
          <q-select
            v-model="zoneId"
            :options="zones"
            option-value="id"
            option-label="name"
            emit-value
            map-options
            autofocus
            dense
            outlined
            :label="t('objects.pickZone.label')"
            :rules="[(v: number | null) => v !== null || t('objects.pickZone.required')]"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps :label="t('objects.pickZone.cancel')" @click="onDialogCancel" />
          <q-btn color="primary" no-caps type="submit" :label="t('objects.pickZone.ok')" />
        </q-card-actions>
      </q-form>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDialogPluginComponent } from 'quasar'
import type { IZoneRef } from '../types/objects'

const props = defineProps<{ zones: IZoneRef[] }>()
defineEmits([...useDialogPluginComponent.emits])
const { t } = useI18n()
const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent()
const zoneId = ref<number | null>(props.zones.length === 1 ? (props.zones[0]?.id ?? null) : null)

/** Conferma la zona scelta (se ce n'è una). */
function confirm(): void {
  if (zoneId.value !== null) onDialogOK(zoneId.value)
}
</script>
