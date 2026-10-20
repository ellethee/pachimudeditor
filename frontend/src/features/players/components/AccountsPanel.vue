<template>
  <div>
    <pachi-table2
      ref="table"
      :url="ACCOUNTS_URL"
      :columns="columns"
      :initial-sort="[{ column: 'username', direction: 'asc' }]"
      :can-edit="allowRow"
      error-banner
      dense
    >
      <template #error="{ error, retry }">
        <table-error :error="error" :retry="retry" />
      </template>
      <template #toolbar-actions="{ api }">
        <q-btn color="primary" :icon="mdiPlus" :label="t('players.accounts.new')" :disable="readOnly" @click="openCreate(api)" />
        <q-btn flat round :icon="mdiRefresh" :aria-label="t('players.reload')" @click="api.reload()" />
      </template>
      <template #body-cell-isBanned="{ slotProps }">
        <q-td :props="slotProps">
          <q-badge
            :color="slotProps.row.isBanned ? 'negative' : 'positive'"
            :label="slotProps.row.isBanned ? t('players.accounts.banned') : t('players.accounts.active')"
          />
        </q-td>
      </template>
      <template #body-cell-actions="{ slotProps, api }">
        <q-td :props="slotProps" auto-width>
          <q-btn flat round dense :icon="mdiEmail" :aria-label="t('players.accounts.editEmail')" :disable="readOnly" @click="editEmail(slotProps.row, api)">
            <q-tooltip>{{ t('players.accounts.editEmail') }}</q-tooltip>
          </q-btn>
          <q-btn flat round dense :icon="mdiKey" :aria-label="t('players.accounts.setPassword')" :disable="readOnly" @click="changePassword(slotProps.row)">
            <q-tooltip>{{ t('players.accounts.setPassword') }}</q-tooltip>
          </q-btn>
          <q-btn
            flat
            round
            dense
            :icon="slotProps.row.isBanned ? mdiAccountCheck : mdiAccountCancel"
            :aria-label="slotProps.row.isBanned ? t('players.accounts.unban') : t('players.accounts.ban')"
            :disable="readOnly" @click="toggleBan(slotProps.row, api)"
          >
            <q-tooltip>{{ slotProps.row.isBanned ? t('players.accounts.unban') : t('players.accounts.ban') }}</q-tooltip>
          </q-btn>
          <q-btn flat round dense :icon="mdiAccountGroup" :aria-label="t('players.accounts.showCharacters')" @click="emit('show-characters', slotProps.row)">
            <q-tooltip>{{ t('players.accounts.showCharacters') }}</q-tooltip>
          </q-btn>
          <q-btn flat round dense :icon="mdiDelete" :aria-label="t('players.delete')" :disable="readOnly" @click="confirmDelete(slotProps.row, api)">
            <q-tooltip>{{ t('players.delete') }}</q-tooltip>
          </q-btn>
        </q-td>
      </template>
    </pachi-table2>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import type { QTableColumn } from 'quasar'
import {
  mdiAccountCancel,
  mdiAccountCheck,
  mdiAccountGroup,
  mdiDelete,
  mdiEmail,
  mdiKey,
  mdiPlus,
  mdiRefresh,
} from '@quasar/extras/mdi-v7'
import { PachiTable2 } from '@ilpachi/pachi-kit/table'
import type { PachiTable2Api, PachiTable2Exposed } from '@ilpachi/pachi-kit/table'
import { describeError } from '../helpers/describe-error'
import { useWorld } from '../../shared/helpers/world-state'
import {
  ACCOUNTS_URL,
  createAccount,
  deleteAccount,
  setAccountBan,
  setAccountPassword,
  updateAccountEmail,
} from '../services/players-api'
import type { IAccount } from '../types/players'
import TableError from '../../shared/components/TableError.vue'

const emit = defineEmits<{ 'show-characters': [account: IAccount] }>()

const { t, d } = useI18n()
const $q = useQuasar()
const { readOnly } = useWorld()
const table = ref<PachiTable2Exposed<IAccount> | null>(null)

/** Serve a tipizzare la tabella su `IAccount` (le azioni di riga sono personalizzate). */
const allowRow = (_row: IAccount): boolean => !readOnly.value

/**
 * Data/ora localizzata o trattino.
 *
 * @param value - ISO string o null
 */
function fmt(value: string | null): string {
  return value ? d(new Date(value), 'short') : '—'
}

const columns = computed<QTableColumn<IAccount>[]>(() => [
  { name: 'username', label: t('players.accounts.username'), field: 'username', align: 'left', sortable: true },
  { name: 'email', label: t('players.accounts.email'), field: (r: IAccount) => r.email ?? '—', align: 'left', sortable: true },
  { name: 'characterCount', label: t('players.accounts.characters'), field: 'characterCount', align: 'right' },
  { name: 'isBanned', label: t('players.accounts.status'), field: 'isBanned', align: 'left', sortable: true },
  { name: 'createdAt', label: t('players.accounts.createdAt'), field: (r: IAccount) => fmt(r.createdAt), align: 'left', sortable: true },
  { name: 'lastLoginAt', label: t('players.accounts.lastLoginAt'), field: (r: IAccount) => fmt(r.lastLoginAt), align: 'left', sortable: true },
  { name: 'actions', label: '', field: 'id', align: 'right' },
])

/**
 * Esegue un'azione e ricarica la tabella; gli errori diventano una notifica.
 *
 * @param action - chiamata al backend
 * @param api - API della tabella
 */
async function run(action: () => Promise<unknown>, api: PachiTable2Api<IAccount>): Promise<void> {
  try {
    await action()
    await api.reload()
  } catch (e) {
    $q.notify({ type: 'negative', message: await describeError(e) })
  }
}

/**
 * Crea un account chiedendo username, password ed email in un unico dialog.
 *
 * @param api - API della tabella
 */
function openCreate(api: PachiTable2Api<IAccount>): void {
  const form = { username: '', password: '', email: '' }
  $q.dialog({
    title: t('players.accounts.new'),
    html: false,
    prompt: { model: '', type: 'text', label: t('players.accounts.username'), isValid: (v: string) => v.trim().length >= 3 },
    cancel: true,
  }).onOk((username: string) => {
    form.username = username.trim()
    $q.dialog({
      title: t('players.accounts.password'),
      prompt: { model: '', type: 'password', label: t('players.accounts.password'), isValid: (v: string) => v.length >= 8 },
      cancel: true,
    }).onOk((password: string) => {
      form.password = password
      $q.dialog({
        title: t('players.accounts.email'),
        message: t('players.accounts.emailOptional'),
        prompt: { model: '', type: 'email', label: t('players.accounts.email') },
        cancel: true,
      }).onOk((email: string) =>
        void run(() => createAccount({ ...form, email: email.trim() === '' ? null : email.trim() }), api),
      )
    })
  })
}

/**
 * Modifica l'email.
 *
 * @param row - account
 * @param api - API della tabella
 */
function editEmail(row: IAccount, api: PachiTable2Api<IAccount>): void {
  $q.dialog({
    title: t('players.accounts.editEmail'),
    message: row.username,
    prompt: { model: row.email ?? '', type: 'email', label: t('players.accounts.email') },
    cancel: true,
  }).onOk((email: string) =>
    void run(() => updateAccountEmail(row.id, email.trim() === '' ? null : email.trim()), api),
  )
}

/**
 * Imposta una nuova password.
 *
 * @param row - account
 */
function changePassword(row: IAccount): void {
  $q.dialog({
    title: t('players.accounts.setPassword'),
    message: row.username,
    prompt: { model: '', type: 'password', label: t('players.accounts.password'), isValid: (v: string) => v.length >= 8 },
    cancel: true,
  }).onOk(async (password: string) => {
    try {
      await setAccountPassword(row.id, password)
      $q.notify({ type: 'positive', message: t('players.accounts.passwordChanged') })
    } catch (e) {
      $q.notify({ type: 'negative', message: await describeError(e) })
    }
  })
}

/**
 * Banna o riabilita l'account.
 *
 * @param row - account
 * @param api - API della tabella
 */
function toggleBan(row: IAccount, api: PachiTable2Api<IAccount>): void {
  void run(() => setAccountBan(row.id, !row.isBanned), api)
}

/**
 * Chiede conferma (con opzione cascata se ha personaggi) ed elimina.
 *
 * @param row - account
 * @param api - API della tabella
 */
function confirmDelete(row: IAccount, api: PachiTable2Api<IAccount>): void {
  const hasCharacters = row.characterCount > 0
  $q.dialog({
    title: t('players.accounts.deleteTitle'),
    message: hasCharacters
      ? t('players.accounts.deleteWithCharacters', { name: row.username, count: row.characterCount })
      : t('players.accounts.deleteMessage', { name: row.username }),
    ...(hasCharacters
      ? { options: { type: 'toggle' as const, model: [], items: [{ label: t('players.accounts.cascade'), value: 'cascade' }] } }
      : {}),
    cancel: true,
  }).onOk((choice: string[] | undefined) => {
    const cascade = Array.isArray(choice) && choice.includes('cascade')
    if (hasCharacters && !cascade) return
    void run(() => deleteAccount(row.id, cascade), api)
  })
}

/** Ricarica la tabella (usabile dal contenitore). */
function reload(): void {
  void table.value?.api.reload()
}

defineExpose({ reload })
</script>
