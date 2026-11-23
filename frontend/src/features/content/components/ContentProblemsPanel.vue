<template>
  <q-card v-if="issues.length > 0" flat bordered data-testid="content-problems">
    <q-card-section class="row items-center q-py-sm">
      <q-icon :name="errors > 0 ? mdiAlertCircle : mdiAlert" :color="errors > 0 ? 'negative' : 'warning'" size="sm" class="q-mr-sm" />
      <div class="text-subtitle2">{{ t('content.problems.title', { errors, warnings }) }}</div>
    </q-card-section>
    <q-separator />
    <q-list dense separator style="max-height: 480px; overflow: auto">
      <template v-for="group in groups" :key="group.code">
        <q-item-label v-if="grouped" header class="row items-center q-gutter-x-sm" data-testid="content-problem-group">
          <q-badge :color="group.severity === 'error' ? 'negative' : 'warning'" :text-color="group.severity === 'error' ? 'white' : 'dark'" :label="group.code" />
          <span>{{ group.rows.length }}</span>
          <span v-if="explain(group.code)" class="text-caption text-grey-8">{{ explain(group.code) }}</span>
        </q-item-label>
        <q-item
          v-for="row in group.rows"
          :key="row.index"
          :clickable="route(row.index) !== null"
          data-testid="content-problem"
          @click="open(row.index)"
        >
          <q-item-section v-if="!grouped" avatar>
            <q-badge :color="row.issue.severity === 'error' ? 'negative' : 'warning'" :text-color="row.issue.severity === 'error' ? 'white' : 'dark'" :label="row.issue.code">
              <q-tooltip v-if="explain(row.issue.code)">{{ explain(row.issue.code) }}</q-tooltip>
            </q-badge>
          </q-item-section>
          <q-item-section>
            <q-item-label>{{ row.issue.message }}</q-item-label>
            <q-item-label v-if="row.issue.file" caption style="font-family: monospace" :title="row.issue.file">
              {{ shortFile(row.issue.file) }}{{ row.issue.line ? `:${row.issue.line}` : '' }}
            </q-item-label>
          </q-item-section>
          <q-item-section v-if="route(row.index) !== null" side>
            <q-icon :name="mdiOpenInNew" size="xs" data-testid="content-problem-open" />
          </q-item-section>
        </q-item>
      </template>
    </q-list>
  </q-card>
</template>

<script setup lang="ts">
/**
 * Pannello dei problemi dei contenuti (gravità, codice, messaggio, file e riga) dell'ultimo controllo del gioco. Un problema il cui
 * file è dell'editor è cliccabile e apre la stanza, il mob, l'oggetto, i reset o la zona. Con `grouped` i problemi sono raggruppati per
 * codice, ognuno con la sua spiegazione; `zoneId` li limita a una zona.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { mdiAlert, mdiAlertCircle, mdiOpenInNew } from '@quasar/extras/mdi-v7'
import { useContentLive } from '../composables/use-content-live'
import { issueRoute } from '../helpers/issue-target'
import type { IContentIssue } from '../types/content-files'

const props = defineProps<{
  /** Raggruppa per codice (pagina «Controllo»). */
  grouped?: boolean
  /** Mostra solo i problemi di questa zona (quelli che l'editor non sa collocare restano esclusi). */
  zoneId?: number | null
}>()

const { t, te } = useI18n()
const router = useRouter()
const { issues, targets, errors, warnings } = useContentLive()

interface IRow {
  issue: IContentIssue
  index: number
}

/** I problemi, filtrati per zona e raggruppati per codice (un unico gruppo senza `grouped`). */
const groups = computed(() => {
  const rows: IRow[] = issues.value
    .map((issue, index) => ({ issue, index }))
    .filter((r) => props.zoneId == null || targets.value[r.index]?.zoneId === props.zoneId)
  if (!props.grouped) return [{ code: '', severity: 'error' as const, rows }]
  const byCode = new Map<string, { code: string; severity: 'error' | 'warning'; rows: IRow[] }>()
  for (const row of rows) {
    const group = byCode.get(row.issue.code) ?? { code: row.issue.code, severity: row.issue.severity, rows: [] }
    group.rows.push(row)
    byCode.set(row.issue.code, group)
  }
  return [...byCode.values()].sort((a, b) => Number(a.severity === 'warning') - Number(b.severity === 'warning') || b.rows.length - a.rows.length)
})

/** Spiegazione del codice nella lingua dell'interfaccia (vuota se non c'è). */
function explain(code: string): string {
  return te(`content.codes.${code}`) ? t(`content.codes.${code}`) : ''
}

/** Gli ultimi tre segmenti del percorso (`zones/Zona/rooms.yaml`): il percorso intero resta nel tooltip. */
function shortFile(file: string): string {
  return file.split('/').slice(-3).join('/')
}

/** Pagina da aprire per il problema `index`, `null` se non si sa dove sta. */
function route(index: number): string | null {
  return issueRoute(targets.value[index] ?? null)
}

/** Apre la voce del problema `index`. */
async function open(index: number): Promise<void> {
  const to = route(index)
  if (to) await router.push(to)
}
</script>
