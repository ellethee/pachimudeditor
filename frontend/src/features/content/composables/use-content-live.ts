import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import { useLive } from '../../playerfiles/helpers/live-state'
import { describeError } from '../helpers/describe-error'
import { reloadIssues } from '../helpers/content-issues'
import { reloadLiveZone } from '../../playerfiles/services/live-api'
import { locateIssues, reloadContent, validateContent } from '../services/content-files-api'
import type { IContentIssue, ILocated, ReloadKind } from '../types/content-files'

/** Problemi dell'ultimo controllo (condivisi fra le pagine dei contenuti). */
const issues = ref<IContentIssue[]>([])
/** `true` dopo almeno un controllo riuscito. */
const checked = ref(false)
const busy = ref(false)
/** Controllo severo: anche i controlli solo informativi (`exit-target-out-of-zone`, `flag-inert`) e gli avvisi fanno `ok = false`. */
const strict = ref(false)
/** Per ogni problema (stesso indice) la voce che lo contiene, risolta dall'editor (`null` finché non arriva o se il file non è suo). */
const targets = ref<(ILocated | null)[]>([])

watch(
  issues,
  async (list) => {
    const withFile = list.map((issue, index) => ({ issue, index })).filter((x) => x.issue.file)
    targets.value = list.map(() => null)
    if (withFile.length === 0) return
    try {
      const found = await locateIssues(withFile.map((x) => ({ file: x.issue.file as string, line: x.issue.line })))
      if (issues.value !== list) return // un controllo più recente ha sostituito l'elenco
      const next: (ILocated | null)[] = list.map(() => null)
      withFile.forEach((x, i) => (next[x.index] = found[i] ?? null))
      targets.value = next
    } catch {
      // senza la risoluzione i problemi restano leggibili (file e riga), solo non cliccabili
    }
  },
  { flush: 'post' }
)

/**
 * Controllo e ricarica a caldo dei contenuti tramite il canale live del gioco (`content.validate`, `content.reload`).
 * Senza canale connesso (o per chi non è superuser) le funzioni non sono offerte: le modifiche valgono al riavvio del gioco.
 *
 * @returns stato condiviso e azioni
 */
export function useContentLive() {
  const { t } = useI18n()
  const $q = useQuasar()
  const live = useLive()
  const commands = computed(() => live.status.value?.commands ?? [])
  const canValidate = computed(() => live.connected.value && commands.value.includes('content.validate'))
  const canReload = computed(() => live.canWrite.value && commands.value.includes('content.reload'))
  const errors = computed(() => issues.value.filter((i) => i.severity === 'error').length)
  const warnings = computed(() => issues.value.length - errors.value)

  /** Chiede al gioco di controllare i file (silenzioso se il canale non c'è). */
  async function validate(): Promise<void> {
    if (!canValidate.value) return
    busy.value = true
    try {
      issues.value = (await validateContent(strict.value)).issues
      checked.value = true
    } catch (error) {
      $q.notify({ type: 'negative', message: await describeError(error) })
    } finally {
      busy.value = false
    }
  }

  /**
   * Chiede al gioco di rileggere i contenuti; se i file non sono validi il gioco resta com'era e i problemi vanno nel pannello.
   * @param kind cosa rileggere
   * @returns `true` se il gioco ha ricaricato
   */
  async function reload(kind: ReloadKind): Promise<boolean> {
    busy.value = true
    try {
      await reloadContent(kind)
      $q.notify({ type: 'positive', message: t('content.live.reloaded') })
      return true
    } catch (error) {
      const found = await reloadIssues(error)
      if (found.length > 0) {
        issues.value = found
        checked.value = true
      }
      $q.notify({ type: 'negative', message: await describeError(error), timeout: 8000 })
      return false
    } finally {
      busy.value = false
    }
  }

  /**
   * Chiede al gioco di rileggere dai file una zona. Se non riesce, i problemi (file e riga) vanno nel pannello.
   * @param vnum vnum della zona
   * @returns `true` se il gioco ha ricaricato
   */
  async function reloadZone(vnum: number): Promise<boolean> {
    try {
      const out = await reloadLiveZone(vnum)
      $q.notify({ type: 'positive', message: t('zones.detail.liveReloaded', { name: out.name, rooms: out.rooms, mobs: out.mobs, objects: out.objects }) })
      return true
    } catch (error) {
      const found = await reloadIssues(error)
      if (found.length > 0) {
        issues.value = found
        checked.value = true
      }
      const where = found.filter((i) => i.severity === 'error').slice(0, 3).map((i) => [i.file ? `${i.file.split('/').slice(-2).join('/')}${i.line ? `:${i.line}` : ''}` : '', i.message].filter(Boolean).join(' '))
      $q.notify({ type: 'negative', message: [await describeError(error), ...where].join('\n'), multiLine: true, timeout: 12000 })
      return false
    }
  }

  return { issues, targets, strict, checked, busy, errors, warnings, canValidate, canReload, validate, reload, reloadZone, refreshStatus: live.refresh }
}
