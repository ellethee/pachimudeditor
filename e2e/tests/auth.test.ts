/** Login, logout, menu e dashboard. */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { BASE_URL, goto, login, loginOk, openSession, rawI18nKey, type Session } from '../support/browser.ts'

describe('autenticazione e dashboard', () => {
  let s: Session
  before(async () => {
    s = await openSession()
  })
  after(async () => {
    await s.close()
  })

  it('una route protetta senza login rimanda alla pagina di accesso', async () => {
    await goto(s.page, '/')
    await s.page.waitForURL(/\/auth\/login/)
    await s.page.getByText('Accedi al tuo account').waitFor()
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('password errata: messaggio tradotto e nessun accesso', async () => {
    s.allow(/401/)
    s.allow(/Login failed/)
    await login(s.page, 'sbagliata-sbagliata')
    await s.page.getByText('Credenziali non valide.').first().waitFor()
    assert.match(s.page.url(), /\/auth\/login/)
  })

  it('login riuscito: dashboard con le 5 schede', async () => {
    await loginOk(s.page)
    for (const title of ['Zone', 'Stanze', 'Mappa stanze', 'Mob', 'Oggetti']) {
      await s.page.locator('main, .q-page, body').getByText(title, { exact: true }).first().waitFor()
    }
    for (const description of [
      'Zone del mondo e relativi script di reset',
      'Stanze, uscite ed extra description',
      'Grafo delle stanze di una zona',
      'Mob prototipo: statistiche, flag e descrizioni',
      'Oggetti prototipo: tipo, flag e valori',
    ]) {
      await s.page.getByText(description).waitFor()
    }
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('le schede della dashboard portano alle pagine', async () => {
    const targets: Array<[string, RegExp]> = [
      ['Zone del mondo e relativi script di reset', /\/zones$/],
      ['Stanze, uscite ed extra description', /\/rooms$/],
      ['Grafo delle stanze di una zona', /\/rooms\/map$/],
      ['Mob prototipo: statistiche, flag e descrizioni', /\/mobs$/],
      ['Oggetti prototipo: tipo, flag e valori', /\/objects$/],
    ]
    for (const [description, url] of targets) {
      await s.page.goto(`${BASE_URL}/`)
      await s.page.getByText(description).click()
      await s.page.waitForURL(url)
    }
  })

  it('ricaricare una route client non da 404 (fallback SPA)', async () => {
    await goto(s.page, '/rooms/map')
    await s.page.getByText('Mappa stanze').first().waitFor()
  })

  it('logout dal menu utente', async () => {
    await goto(s.page, '/')
    await s.page.getByText('E', { exact: true }).first().click()
    await s.page.getByText('e2e-user').first().waitFor()
    await s.page.getByText(/Disconnetti/i).first().click()
    await s.page.waitForURL(/\/auth\/login/)
    await goto(s.page, '/zones')
    await s.page.waitForURL(/\/auth\/login/)
  })

  it('nessun errore di console imprevisto', () => {
    assert.deepEqual(s.errors, [])
  })
})
