/**
 * Utility browser per i test e2e: browser headless proprio con profilo temporaneo (default) oppure
 * connessione a un Chromium gia' avviato (E2E_CDP_URL), login, raccolta errori di console e controlli comuni.
 *
 * Regole: il browser proprio e il suo profilo vengono eliminati a fine sessione (e all'uscita del processo);
 * su un browser esterno si apre SEMPRE un nuovo contesto e i tab esistenti non si toccano.
 */
import { existsSync } from 'node:fs'
import { chromium, type Browser, type BrowserContext, type Locator, type Page } from 'playwright-core'
import { credentials } from './stack.ts'

/** Se impostata, ci si collega a quel browser gia' in esecuzione (CDP); altrimenti se ne lancia uno headless proprio. */
export const CDP_URL = process.env.E2E_CDP_URL

/** Eseguibile del browser headless proprio (override con E2E_CHROME_PATH). */
function chromePath(): string {
  const candidates = [process.env.E2E_CHROME_PATH, '/usr/bin/google-chrome', '/usr/bin/chromium-browser', '/usr/bin/chromium']
  const found = candidates.find((path) => path && existsSync(path))
  if (!found) throw new Error('Nessun Chrome/Chromium trovato: imposta E2E_CHROME_PATH o E2E_CDP_URL')
  return found
}

/** URL base dello stack, impostato da `run.ts`. */
export const BASE_URL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:8124'

/** Chiavi i18n non risolte: `zones.form.name`, `rooms.map.title`, ... */
const RAW_KEY = /\b(?:zones|rooms|mobs|objects|worlds|extra|world|players|instances|transfer|content|auth|errors|common|menu|dashboard|app)\.[a-zA-Z]+(?:\.[a-zA-Z]+)+\b/

/** Una sessione di browser isolata (contesto + pagina) con raccolta degli errori. */
export interface Session {
  browser: Browser
  context: BrowserContext
  page: Page
  /** Errori di console / pagina raccolti finora (oltre a quelli ammessi). */
  errors: string[]
  /** Ammette gli errori di console che corrispondono (es. il 409 atteso di un test negativo). */
  allow: (pattern: RegExp) => void
  /** Chiude il contesto e il browser proprio (profilo incluso); su un browser esterno si limita a disconnettersi. */
  close: () => Promise<void>
}

/**
 * Lancia un Chrome headless (profilo temporaneo) o si collega via CDP se E2E_CDP_URL e' impostata,
 * poi apre un nuovo contesto con un nuovo tab.
 * @returns la sessione pronta all'uso
 */
export async function openSession(): Promise<Session> {
  const browser = CDP_URL
    ? await chromium.connectOverCDP(CDP_URL)
    : await chromium.launch({ executablePath: chromePath(), headless: true })
  const context = await browser.newContext({ viewport: { width: 1400, height: 1000 }, locale: 'it-IT' })
  const page = await context.newPage()
  const errors: string[] = []
  const allowed: RegExp[] = []
  const record = (text: string): void => {
    if (!allowed.some((re) => re.test(text))) errors.push(text)
  }
  page.on('console', (message) => {
    const text = message.text()
    if (message.type() === 'error') record(`console.error: ${text}`)
    else if (message.type() === 'warning' && /i18n|Not found '.*' key|intlify/i.test(text)) record(`i18n: ${text}`)
  })
  page.on('pageerror', (error) => record(`pageerror: ${error.message}`))
  page.setDefaultTimeout(15_000)
  return {
    browser,
    context,
    page,
    errors,
    allow: (pattern) => void allowed.push(pattern),
    close: async () => {
      await context.close().catch(() => undefined)
      await browser.close().catch(() => undefined)
    },
  }
}

/**
 * Esegue il login dall'interfaccia con l'utente di test.
 * @param page pagina da usare
 * @param password password da inserire (default: quella dell'utente di test)
 */
export async function login(page: Page, password: string = credentials.password): Promise<void> {
  await loginAt(page, BASE_URL, password)
}

/**
 * Login dall'interfaccia su uno stack qualsiasi.
 * @param page pagina da usare
 * @param baseUrl URL base dello stack
 * @param password password da inserire (default: quella dell'utente di test)
 */
export async function loginAt(page: Page, baseUrl: string, password: string = credentials.password): Promise<void> {
  await page.goto(`${baseUrl}/`)
  await page.getByLabel('Utente').fill(credentials.username)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: /Accedi/ }).click()
}

/**
 * Login riuscito: attende la dashboard.
 * @param page pagina da usare
 */
export async function loginOk(page: Page): Promise<void> {
  await login(page)
  await page.getByText('Overview').first().waitFor()
}

/**
 * Naviga a una route dell'SPA (history mode) con un caricamento completo.
 * @param page pagina
 * @param path route, es. `/zones`
 */
export async function goto(page: Page, path: string): Promise<void> {
  await page.goto(`${BASE_URL}${path}`)
}

/**
 * Verifica che nella pagina non compaiano chiavi i18n grezze (traduzione mancante).
 * @param page pagina
 * @returns il testo trovato, o `null`
 */
export async function rawI18nKey(page: Page): Promise<string | null> {
  const text = await page.locator('body').innerText()
  return RAW_KEY.exec(text)?.[0] ?? null
}

/** Riga di una tabella pachi-table2 che contiene il testo dato. */
export function tableRow(page: Page, text: string | RegExp): Locator {
  return page.locator('table tbody tr', { hasText: text })
}

/** Dialog aperto (ultimo). */
export function dialog(page: Page): Locator {
  return page.locator('.q-dialog').last()
}

/**
 * Salva il dialog di modifica (pulsante "Salva modifiche").
 * @param page pagina
 */
export async function saveDialog(page: Page): Promise<void> {
  await page.getByLabel('Salva modifiche').click()
}

/**
 * Conferma un dialog di conferma (pulsante positivo con icona, oppure "OK").
 * @param page pagina
 */
export async function confirm(page: Page): Promise<void> {
  const scope = page.locator('.q-dialog').last()
  await scope.locator('button.text-positive').or(scope.getByRole('button', { name: 'OK', exact: true })).last().click()
}

/**
 * Attende che non ci siano dialog aperti.
 * @param page pagina
 */
export async function waitDialogsClosed(page: Page): Promise<void> {
  await page.locator('.q-dialog').first().waitFor({ state: 'detached' })
}

/**
 * Inserisce un chip in un campo flag (testo + Invio).
 * @param page pagina
 * @param label etichetta del campo
 * @param value flag da aggiungere
 */
export async function addFlag(page: Page, label: string, value: string): Promise<void> {
  const input = page.getByLabel(label)
  await input.click()
  await input.fill(value)
  await input.press('Enter')
}

/**
 * Sceglie un'opzione in una q-select dato il suo label.
 * @param page pagina
 * @param label etichetta della select
 * @param option testo (o regex) dell'opzione
 */
export async function pickOption(page: Page, label: string, option: string | RegExp): Promise<void> {
  await page.getByLabel(label, { exact: true }).click()
  await page.locator('.q-menu .q-item', { hasText: option }).first().click()
}

/**
 * Chiude il dialog di modifica scartando le modifiche non salvate (conferma "OK").
 * @param page pagina
 */
export async function closeDiscarding(page: Page): Promise<void> {
  await page.getByLabel('Chiudi').first().click()
  await page.getByRole('button', { name: 'OK', exact: true }).click()
  await waitDialogsClosed(page)
}

/**
 * Chiude il dialog di errore globale ("OK") e attende che non ce ne siano piu' aperti.
 * @param page pagina
 */
export async function dismissError(page: Page): Promise<void> {
  await page.locator('.q-dialog').last().getByRole('button', { name: 'OK', exact: true }).click()
  await waitDialogsClosed(page)
}
