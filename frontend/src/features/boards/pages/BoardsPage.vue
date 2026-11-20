<template>
  <div class="q-pa-md column q-gutter-y-md">
    <q-tabs v-model="tab" dense align="left" class="text-primary" data-testid="boards-tabs">
      <q-tab name="boards" :label="t('boards.tabs.boards')" data-testid="boards-tab-boards" />
      <q-tab name="mail" :label="t('boards.tabs.mail')" data-testid="boards-tab-mail" />
    </q-tabs>
    <q-banner v-if="error" rounded class="bg-negative text-white" data-testid="boards-error">{{ error }}</q-banner>

    <template v-if="tab === 'boards'">
      <q-banner v-if="boards && !boards.boardTable" rounded class="bg-warning text-dark" data-testid="boards-no-table">{{ t('boards.noTable') }}</q-banner>

      <template v-else-if="!selected">
        <div class="row items-center q-gutter-sm">
          <q-input v-model="boardSearch" dense outlined clearable class="col-12 col-sm-5 col-md-4" :label="t('boards.search')" data-testid="boards-filter" />
          <q-space />
          <q-btn flat no-caps :icon="mdiRefresh" :label="t('boards.refresh')" :loading="loading" data-testid="boards-refresh" @click="load" />
        </div>
        <q-table
          flat
          bordered
          dense
          row-key="boardId"
          :rows="boardRows"
          :columns="boardColumns"
          :loading="loading"
          :pagination="{ rowsPerPage: 50 }"
          :no-data-label="t('boards.empty')"
          data-testid="boards-table"
        >
          <template #body="p">
            <q-tr :props="p" class="cursor-pointer" data-testid="board-row" @click="openBoard(p.row)">
              <q-td key="boardId" :props="p">
                {{ p.row.boardId }}
                <q-badge v-if="p.row.orphan" color="warning" text-color="dark" class="q-ml-sm" data-testid="board-orphan">{{ t('boards.orphan') }}</q-badge>
              </q-td>
              <q-td key="objects" :props="p">
                <span v-if="!p.row.objects.length" class="text-grey">{{ t('boards.noObjects') }}</span>
                <span v-for="(o, i) in p.row.objects" :key="o.vnum">{{ i ? ', ' : '' }}#{{ o.vnum }} {{ o.name }} ({{ o.zoneName }})</span>
              </q-td>
              <q-td key="count" :props="p">{{ p.row.count }}</q-td>
              <q-td key="limit" :props="p">{{ p.row.maxMessages ?? '' }}</q-td>
            </q-tr>
          </template>
        </q-table>
      </template>

      <template v-else>
        <div class="row items-center q-gutter-sm">
          <q-btn flat no-caps :icon="mdiArrowLeft" :label="t('boards.back')" data-testid="board-back" @click="selected = null" />
          <div class="text-subtitle1" data-testid="board-title">{{ t('boards.messages', { id: selected.boardId }) }}</div>
          <q-input v-model="search" dense outlined clearable debounce="200" class="col-12 col-sm-4" :label="t('boards.search')" data-testid="board-search" />
        </div>
        <div class="text-caption text-grey">{{ t('boards.readOnlyNote') }}</div>
        <q-table
          flat
          bordered
          dense
          row-key="id"
          :rows="messages"
          :columns="messageColumns"
          :loading="loadingMessages"
          :pagination="{ rowsPerPage: 25 }"
          :no-data-label="t('boards.noMessages')"
          data-testid="board-messages"
        >
          <template #body="p">
            <q-tr :props="p" class="cursor-pointer" data-testid="board-message" @click="p.expand = !p.expand">
              <q-td key="number" :props="p">{{ p.row.number }}</q-td>
              <q-td key="author" :props="p">{{ p.row.author }}</q-td>
              <q-td key="date" :props="p">{{ formatDate(p.row.createdAt) }}</q-td>
              <q-td key="title" :props="p">{{ p.row.title }}</q-td>
            </q-tr>
            <q-tr v-show="p.expand" :props="p">
              <q-td colspan="100%" class="text-body2" style="white-space: pre-wrap" data-testid="board-message-text">{{ p.row.text }}</q-td>
            </q-tr>
          </template>
        </q-table>
      </template>
    </template>

    <template v-else>
      <q-banner v-if="mail && !mail.available" rounded class="bg-warning text-dark" data-testid="mail-no-table">{{ t('boards.noMailTable') }}</q-banner>
      <template v-else>
        <div class="text-caption text-grey" data-testid="mail-privacy">{{ t('boards.mail.privacy') }}</div>
        <div class="row items-center q-gutter-sm">
          <q-input v-model="mailSearch" dense outlined clearable class="col-12 col-sm-4" :label="t('boards.mail.search')" data-testid="mail-search" />
          <div class="text-subtitle2" data-testid="mail-total">{{ t('boards.mail.total', { count: mail?.total ?? 0 }) }}</div>
        </div>
        <q-table
          flat
          bordered
          dense
          row-key="recipient"
          :rows="mailRows"
          :columns="mailColumns"
          :loading="loadingMail"
          :pagination="{ rowsPerPage: 50 }"
          :no-data-label="t('boards.mail.empty')"
          data-testid="mail-table"
        />
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * Bacheche e posta del gioco, in sola lettura: elenco delle bacheche (oggetti BOARD e `board_id` presenti nel DB) con i conteggi,
 * messaggi di una bacheca con ricerca, e quante lettere aspettano ogni giocatore (mai il testo). La moderazione passerà dal canale
 * live, perché il gioco tiene i messaggi in memoria.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { mdiArrowLeft, mdiRefresh } from '@quasar/extras/mdi-v7'
import { describeError } from '../../content/helpers/describe-error'
import { getMail, listBoardMessages, listBoards } from '../services/boards-api'
import type { IBoardItem, IBoardMessage, IBoardsOut, IMailOut } from '../types/boards'

const { t, d } = useI18n()

const tab = ref<'boards' | 'mail'>('boards')
const error = ref('')
const loading = ref(false)
const boards = ref<IBoardsOut | null>(null)
const boardSearch = ref('')
const selected = ref<IBoardItem | null>(null)
const search = ref('')
const messages = ref<IBoardMessage[]>([])
const loadingMessages = ref(false)
const mail = ref<IMailOut | null>(null)
const mailSearch = ref('')
const loadingMail = ref(false)

/** Colonne di una tabella `q-table` con le etichette `boards.<group>.<name>`. */
function cols(group: string, names: string[]) {
  return names.map((name) => ({ name, label: t(`boards.${group}.${name}`), field: name, align: 'left' as const, sortable: true }))
}

const boardColumns = computed(() => cols('columns', ['boardId', 'objects', 'count', 'limit']))
const messageColumns = computed(() => cols('message', ['number', 'author', 'date', 'title']))
const mailColumns = computed(() => cols('mail', ['recipient', 'count']))

/** Bacheche filtrate per id, oggetto o zona. */
const boardRows = computed(() => {
  const needle = (boardSearch.value ?? '').trim().toLowerCase()
  const all = boards.value?.boards ?? []
  if (!needle) return all
  return all.filter((b) => [b.boardId, ...b.objects.map((o) => `${o.vnum} ${o.name} ${o.zoneName}`)].join(' ').toLowerCase().includes(needle))
})

/** Destinatari filtrati per nome. */
const mailRows = computed(() => {
  const needle = (mailSearch.value ?? '').trim().toLowerCase()
  const all = mail.value?.recipients ?? []
  return needle ? all.filter((r) => r.recipient.toLowerCase().includes(needle)) : all
})

/** Data e ora locali di un messaggio. */
function formatDate(iso: string): string {
  return d(new Date(iso), 'short')
}

/** Carica l'elenco delle bacheche. */
async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    boards.value = await listBoards()
  } catch (e) {
    error.value = await describeError(e)
  } finally {
    loading.value = false
  }
}

/** Carica i messaggi della bacheca aperta (con la ricerca corrente). */
async function loadMessages(): Promise<void> {
  if (!selected.value) return
  loadingMessages.value = true
  error.value = ''
  try {
    messages.value = await listBoardMessages(selected.value.boardId, (search.value ?? '').trim())
  } catch (e) {
    error.value = await describeError(e)
  } finally {
    loadingMessages.value = false
  }
}

/** Apre i messaggi di una bacheca. */
function openBoard(board: IBoardItem): void {
  search.value = ''
  selected.value = board
}

/** Carica i conteggi della posta. */
async function loadMail(): Promise<void> {
  loadingMail.value = true
  error.value = ''
  try {
    mail.value = await getMail()
  } catch (e) {
    error.value = await describeError(e)
  } finally {
    loadingMail.value = false
  }
}

watch([selected, search], () => void loadMessages())
watch(tab, (value) => {
  if (value === 'mail' && !mail.value) void loadMail()
})
onMounted(() => void load())
</script>
