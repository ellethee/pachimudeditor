<template>
  <div class="column q-gutter-y-md" data-testid="convert-report">
    <q-banner v-for="(e, i) in report.errors" :key="`e${i}`" rounded class="bg-negative text-white" data-testid="report-error">
      {{ e.message || e.code }}
    </q-banner>
    <q-banner v-if="report.rollbackErrors.length" rounded class="bg-orange-3 text-dark">
      <div class="text-weight-medium">{{ t('convert.report.rollbackErrors') }}</div>
      <div v-for="(e, i) in report.rollbackErrors" :key="i">{{ e.message || e.code }}</div>
    </q-banner>

    <div>
      <div class="text-subtitle1">{{ t('convert.report.zones') }}</div>
      <q-markup-table flat bordered dense separator="horizontal">
        <thead>
          <tr>
            <th class="text-left">{{ t('convert.report.columns.zone') }}</th>
            <th class="text-left">{{ t('convert.report.columns.action') }}</th>
            <th class="text-left">{{ t('convert.report.columns.source') }}</th>
            <th class="text-left">{{ t('convert.report.columns.target') }}</th>
            <th class="text-right">{{ t('convert.report.columns.offset') }}</th>
            <th v-for="k in countKeys" :key="k" class="text-right">{{ t(`convert.report.columns.${k}`) }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="z in report.zones" :key="z.sourceZoneId" data-testid="report-zone">
            <td>{{ z.name }}</td>
            <td><q-badge :color="actionColor[z.action]" :label="t(`convert.report.actions.${z.action}`)" /></td>
            <td>{{ z.sourceVnum }} ({{ z.sourceBottomVnum }}–{{ z.sourceTopVnum }})</td>
            <td>{{ z.targetVnum }} ({{ z.bottomVnum }}–{{ z.topVnum }})</td>
            <td class="text-right">{{ z.offset }}</td>
            <td v-for="k in countKeys" :key="k" class="text-right">{{ z.counts[k] ?? '–' }}</td>
          </tr>
        </tbody>
      </q-markup-table>
    </div>

    <div>
      <div class="text-subtitle1">{{ t('convert.report.totals') }}</div>
      <q-markup-table flat bordered dense separator="horizontal">
        <thead>
          <tr>
            <th class="text-left">{{ t('convert.report.columns.kind') }}</th>
            <th v-for="c in totalCols" :key="c" class="text-right">{{ t(`convert.report.columns.${c}`) }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(counts, kind) in report.totals" :key="kind" :data-testid="`total-${kind}`">
            <td>{{ t(`convert.report.kinds.${kind}`) }}</td>
            <td v-for="c in totalCols" :key="c" class="text-right">{{ counts[c] }}</td>
          </tr>
        </tbody>
      </q-markup-table>
    </div>

    <q-banner v-if="report.conflicts.length" rounded class="bg-orange-2 text-dark" data-testid="report-conflicts">
      <div class="text-weight-medium">{{ t('convert.report.conflicts') }}</div>
      <ul class="q-my-none">
        <li v-for="(c, i) in report.conflicts" :key="i">
          {{ t(`convert.report.conflictKinds.${c.kind}`, { other: c.otherZone ?? '', entity: c.entity ?? '', vnum: c.vnum ?? '' }) }}
          <span v-if="c.resolved">({{ t('convert.report.resolved') }})</span>
        </li>
      </ul>
    </q-banner>

    <div data-testid="report-losses">
      <div class="text-subtitle1">{{ t('convert.report.losses') }}</div>
      <div v-if="!groups.length" class="text-grey-8">{{ t('convert.report.noLosses') }}</div>
      <q-list v-else bordered separator dense>
        <q-expansion-item v-for="g in groups" :key="g.key" dense :header-class="`bg-${severityColor[g.severity]}-1`" data-testid="loss-group">
          <template #header>
            <q-item-section avatar>
              <q-badge :color="severityColor[g.severity]" :label="t(`convert.report.severity.${g.severity}`)" />
            </q-item-section>
            <q-item-section>{{ g.message }}</q-item-section>
            <q-item-section side>
              <span>{{ t(`convert.report.entities.${g.entity}`) }} × {{ g.count }}</span>
            </q-item-section>
          </template>
          <div class="q-pa-sm text-caption">{{ t('convert.report.examples') }} {{ g.examples.join(', ') }}</div>
        </q-expansion-item>
      </q-list>
    </div>

    <div v-if="remapKinds.length">
      <div class="text-subtitle1">{{ t('convert.report.remap') }}</div>
      <div class="row q-col-gutter-md">
        <div v-for="k in remapKinds" :key="k.kind" class="col-12 col-md-4">
          <div class="text-caption">{{ t(`convert.report.kinds.${k.kind}`) }} — {{ t('convert.report.remapNote', { n: k.shown.length, total: k.total }) }}</div>
          <q-markup-table flat bordered dense style="max-height: 240px; overflow: auto">
            <thead>
              <tr>
                <th class="text-left">{{ t('convert.report.columns.from') }}</th>
                <th class="text-left">{{ t('convert.report.columns.to') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="[from, to] in k.shown" :key="from">
                <td>{{ from }}</td>
                <td>{{ to }}</td>
              </tr>
            </tbody>
          </q-markup-table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/** Rapporto di una conversione: zone, totali, conflitti, perdite raggruppate per gravita'/tipo/codice e tabella dei vnum. */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { IConvertReport, ILossItem, Severity } from '../types/convert'

const props = defineProps<{ report: IConvertReport }>()
const { t } = useI18n()

const countKeys = ['rooms', 'mobs', 'objects', 'exits', 'extraDescriptions', 'resets'] as const
const totalCols = ['create', 'replace', 'skip', 'dropped'] as const
const actionColor = { create: 'positive', replace: 'warning', skip: 'grey', blocked: 'negative' } as const
const severityColor: Record<Severity, string> = { info: 'blue', warning: 'orange', dropped: 'red' }
const severityOrder: Record<Severity, number> = { dropped: 0, warning: 1, info: 2 }

interface ILossGroup {
  key: string
  severity: Severity
  entity: string
  count: number
  message: string
  examples: string[]
}

/** Perdite raggruppate per (gravita', tipo, codice): una riga per gruppo con il numero e qualche esempio. */
const groups = computed<ILossGroup[]>(() => {
  const map = new Map<string, ILossGroup>()
  for (const item of props.report.losses as ILossItem[]) {
    const key = `${item.severity}|${item.entity}|${item.code}`
    let group = map.get(key)
    if (!group) {
      group = { key, severity: item.severity, entity: item.entity, count: 0, message: item.message || item.code, examples: [] }
      map.set(key, group)
    }
    group.count += 1
    if (group.examples.length < 8) group.examples.push(item.vnum !== null ? String(item.vnum) : item.index !== null ? `#${item.index}` : '-')
  }
  return [...map.values()].sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity] || b.count - a.count)
})

const REMAP_LIMIT = 100
/** Tabella dei vnum: prime `REMAP_LIMIT` voci per tipo. */
const remapKinds = computed(() =>
  Object.entries(props.report.remap)
    .map(([kind, table]) => {
      const entries = Object.entries(table)
      return { kind, total: entries.length, shown: entries.slice(0, REMAP_LIMIT) }
    })
    .filter((k) => k.total > 0),
)
</script>
