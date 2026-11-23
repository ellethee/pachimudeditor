import type { IStyleLimits } from '../../content/types/content-files'

/** Funzione di traduzione (`t` di vue-i18n). */
type Translate = (key: string, params?: Record<string, unknown>) => string

/** Testi di una voce da controllare; i campi mancanti si saltano. */
export interface IStyleRecord {
  /** Titolo della stanza. */
  name?: string
  /** Descrizione della stanza. */
  description?: string
  /** Parole chiave del mob o dell'oggetto. */
  keywords?: string
  shortDescription?: string
  longDescription?: string
}

/** Minuscolo e senza accenti, per confrontare nomi e parole chiave come fa il gioco. */
function plain(text: string): string {
  return text
    .toLowerCase()
    .replace(/ø/g, 'o')
    .replace(/æ/g, 'ae')
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
}

/** Le parole (lettere e cifre) di un testo, normalizzate. */
function words(text: string): string[] {
  return plain(text).match(/\w+/g) ?? []
}

/**
 * Avvisi di stile di una voce (i consigli di Clessidra che il gioco riporta come `style-*`): non bloccano il salvataggio. La fonte della
 * verità resta `content.validate`: questa è una copia veloce, calcolata mentre si scrive, con le stesse soglie del mondo.
 *
 * @param kind tipo di voce
 * @param record testi della voce
 * @param limits soglie (`GET /api/content/checks/style`)
 * @param t traduzione
 * @returns un messaggio per ogni consiglio non rispettato (vuoto = tutto a posto)
 */
export function styleWarnings(kind: 'room' | 'mob' | 'object', record: IStyleRecord, limits: IStyleLimits, t: Translate): string[] {
  if (!limits.enabled) return []
  const out: string[] = []
  if (kind === 'room') {
    const name = (record.name ?? '').trim()
    if (name.length > limits.roomNameMax) out.push(t('style.roomNameLong', { n: name.length, max: limits.roomNameMax }))
    else if (name.endsWith('.')) out.push(t('style.roomNamePeriod'))
    else if (name && name.charAt(0) !== name.charAt(0).toUpperCase()) out.push(t('style.roomNameLower'))
    const lines = (record.description ?? '').split('\n').filter((l) => l.trim())
    const count = lines.reduce((sum, l) => sum + Math.max(1, Math.ceil(l.trimEnd().length / limits.descriptionWidth)), 0)
    if (count < limits.descriptionMinLines || count > limits.descriptionMaxLines) {
      out.push(t('style.roomLines', { n: count, min: limits.descriptionMinLines, max: limits.descriptionMaxLines, width: limits.descriptionWidth }))
    } else if (lines.some((l) => l.trimEnd().length > limits.descriptionWidth)) {
      out.push(t('style.roomWidth', { width: limits.descriptionWidth }))
    }
    const banned = new Set(limits.timeWords.map(plain))
    const found = [...new Set(words(`${record.name ?? ''} ${record.description ?? ''}`).filter((w) => banned.has(w)))].sort()
    if (found.length) out.push(t('style.timeWords', { words: found.join(', ') }))
    return out
  }
  const short = (record.shortDescription ?? '').trim()
  const long = (record.longDescription ?? '').trim()
  const keywords = new Set(words(record.keywords ?? ''))
  const first = words(short)[0] ?? ''
  if (short.length > limits.shortMax) out.push(t('style.shortLong', { n: short.length, max: limits.shortMax }))
  else if (short.endsWith('.')) out.push(t('style.shortPeriod'))
  else if (short && short.charAt(0) !== short.charAt(0).toLowerCase() && !keywords.has(first)) out.push(t('style.shortUpper'))
  const problems: string[] = []
  if (long.length > limits.longMax) problems.push(t('style.longLong', { n: long.length, max: limits.longMax }))
  if (long && long.charAt(0) !== long.charAt(0).toUpperCase()) problems.push(t('style.longLower'))
  if (long && !long.endsWith('.')) problems.push(t('style.longNoPeriod'))
  if (long && keywords.size && !words(long).some((w) => keywords.has(w))) problems.push(t('style.longNoKeyword'))
  if (problems.length) out.push(t('style.longProblems', { problems: problems.join('; ') }))
  if (kind === 'mob' && (record.keywords ?? '').split(/\s+/).slice(1).some((w) => w && w.charAt(0) !== w.charAt(0).toLowerCase())) out.push(t('style.mobKeywords'))
  return out
}
