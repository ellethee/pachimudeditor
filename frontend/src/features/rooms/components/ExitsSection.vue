<template>
  <div>
    <div class="text-subtitle1 q-mb-sm">{{ t('rooms.exits.title') }}</div>
    <q-markup-table flat dense>
      <thead>
        <tr>
          <th class="text-left">{{ t('rooms.exits.direction') }}</th>
          <th class="text-left">{{ t('rooms.exits.present') }}</th>
          <th class="text-left">{{ t('rooms.exits.target') }}</th>
          <th class="text-left">{{ t('rooms.exits.door') }}</th>
          <th class="text-left">{{ t('rooms.exits.open') }}</th>
          <th class="text-left">{{ t('rooms.exits.locked') }}</th>
          <th class="text-left">{{ t('rooms.exits.keyVnum') }}</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="row in state.rows" :key="row.direction">
        <tr>
          <td>{{ directionLabel(row.direction) }}</td>
          <td><q-checkbox v-model="row.hasExit" /></td>
          <td>
            <q-select
              v-model="row.targetRoomId"
              :options="filteredRooms"
              option-value="id"
              option-label="label"
              emit-value
              map-options
              dense
              clearable
              use-input
              input-debounce="0"
              :disable="!row.hasExit"
              style="min-width: 220px"
              @filter="filterRooms"
            />
          </td>
          <td>
            <q-select
              v-model="row.doorFlag"
              :options="doorOptions"
              option-value="value"
              option-label="label"
              emit-value
              map-options
              dense
              :disable="!row.hasExit"
              style="min-width: 150px"
            />
          </td>
          <td><q-checkbox v-model="row.isOpen" :disable="!row.hasExit" /></td>
          <td><q-checkbox v-model="row.isLocked" :disable="!row.hasExit" /></td>
          <td>
            <q-input
              v-model.number="row.keyVnum"
              type="number"
              dense
              :disable="!row.hasExit"
              style="width: 100px"
            />
          </td>
        </tr>
        <tr v-if="row.hasExit" class="pachi-exit-details">
          <td></td>
          <td colspan="6">
            <div class="row q-col-gutter-sm">
              <div class="col-12 col-sm-4">
                <q-input
                  :model-value="row.keywords"
                  dense
                  outlined
                  stack-label
                  :label="t('rooms.exits.keywords')"
                  :hint="t('rooms.exits.keywordsHint')"
                  @update:model-value="row.keywords = emptyToNull($event)"
                />
              </div>
              <div class="col-12 col-sm-8">
                <q-input
                  :model-value="row.description"
                  dense
                  outlined
                  stack-label
                  autogrow
                  :label="t('rooms.exits.description')"
                  :hint="t('rooms.exits.descriptionHint')"
                  @update:model-value="row.description = emptyToNull($event)"
                />
              </div>
              <div v-for="field in extraFields" :key="field.name" class="col-12 col-sm-4" data-test="exit-extra">
                <q-checkbox
                  v-if="field.type === 'boolean'"
                  :model-value="row.extra?.[field.name] === true"
                  dense
                  @update:model-value="setExtra(row, field, $event as unknown as string)"
                  :disable="field.readOnly"
                  :label="extraLabel(field)"
                />
                <q-input
                  v-else
                  :model-value="row.extra?.[field.name] as string | number | null"
                  :type="field.type === 'number' ? 'number' : 'text'"
                  dense
                  outlined
                  stack-label
                  :disable="field.readOnly"
                  :label="extraLabel(field)"
                  @update:model-value="setExtra(row, field, $event)"
                />
              </div>
            </div>
          </td>
        </tr>
        </template>
      </tbody>
    </q-markup-table>
  </div>
</template>

<script setup lang="ts">
/**
 * Sezione di `PachiEditDialog`: una riga per direzione con presenza, destinazione, porta,
 * stato e vnum chiave; per le uscite presenti una seconda riga con parole chiave e descrizione. Lo stato è `{ rows }` (una riga per direzione).
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSection } from '@ilpachi/pachi-kit/edit-dialog'
import type { IExtraFieldDescriptor } from '../../shared/types/worlds'
import type { IEnumOption, IExitRow, IRoomOption } from '../types/rooms'

interface IExitsState {
  rows: IExitRow[]
}

const props = withDefaults(defineProps<{
  initialValue?: IExitsState
  directionOptions: IEnumOption[]
  doorOptions: IEnumOption[]
  roomOptions: IRoomOption[]
  /** Campi `extra` delle uscite dichiarati dal mondo (numeri, testi e booleani; gli altri tipi non sono modificabili qui). */
  extraFields?: IExtraFieldDescriptor[]
}>(), { extraFields: () => [] })

const { t, te } = useI18n()
const { state, reset, commit, getResults, hasChanges } = useSection<IExitsState>(
  { rows: [] },
  { initialValue: () => props.initialValue },
)

const filteredRooms = ref<IRoomOption[]>(props.roomOptions)

/** Etichetta della direzione (dal backend) o il valore numerico se sconosciuta. */
function directionLabel(direction: number): string {
  return props.directionOptions.find((option) => option.value === direction)?.label ?? String(direction)
}

/**
 * Etichetta di un campo `extra` dell'uscita (chiave i18n del backend, altrimenti il nome).
 *
 * @param field - descrittore del campo
 */
function extraLabel(field: IExtraFieldDescriptor): string {
  return te(field.labelKey) ? t(field.labelKey) : field.name
}

/**
 * Aggiorna un campo `extra` dell'uscita (numero o testo; `null` se vuoto e annullabile).
 *
 * @param row - riga dell'uscita
 * @param field - descrittore del campo
 * @param value - valore dell'input
 */
function setExtra(row: IExitRow, field: IExtraFieldDescriptor, value: string | number | null): void {
  row.extra ??= {}
  if (field.type === 'boolean') row.extra[field.name] = Boolean(value)
  else if (value === '' || value === null) row.extra[field.name] = field.nullable ? null : undefined
  else row.extra[field.name] = field.type === 'number' ? Number(value) : value
}

/**
 * Il testo vuoto di un campo opzionale diventa `null` (come atteso dal backend).
 *
 * @param value - valore dell'input
 */
function emptyToNull(value: string | number | null): string | null {
  const text = value === null ? '' : String(value)
  return text === '' ? null : text
}

/**
 * Filtra le stanze di destinazione per testo (vnum o nome).
 *
 * @param value - testo digitato
 * @param update - callback di QSelect per applicare il filtro
 */
function filterRooms(value: string, update: (fn: () => void) => void): void {
  update(() => {
    const needle = value.trim().toLowerCase()
    filteredRooms.value = needle
      ? props.roomOptions.filter((option) => option.label.toLowerCase().includes(needle))
      : props.roomOptions
  })
}

defineExpose({ reset, commit, getResults, hasChanges: () => hasChanges.value })
</script>
