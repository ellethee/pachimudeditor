/** Sessione con refresh token in cookie HttpOnly: niente token nel browser, ricarica, piu' schede, logout, CSRF. */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import type { Page } from 'playwright-core'
import { goto, loginOk, openSession, type Session } from '../support/browser.ts'

/** Naviga e attende che il refresh silenzioso iniziale sia finito (un reload subito dopo il load perde il cookie ruotato). */
async function settled(page: Page, path: string): Promise<void> {
  await goto(page, path)
  await page.waitForLoadState('networkidle')
}

describe('sessione con cookie di refresh', () => {
  let s: Session
  before(async () => {
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await s.close()
  })

  it('nessun token in web storage; il cookie e HttpOnly e non e leggibile da JS', async () => {
    const stored = await s.page.evaluate(() => ({
      local: { ...localStorage },
      session: { ...sessionStorage },
      cookie: document.cookie,
    }))
    const dump = JSON.stringify([stored.local, stored.session])
    assert.doesNotMatch(dump, /refresh|eyJ/i, 'nessun token (JWT) in localStorage/sessionStorage')
    assert.doesNotMatch(stored.cookie, /refresh/i)
    const cookie = (await s.context.cookies()).find((c) => c.name === 'pachifast_refresh')
    assert.ok(cookie, 'cookie di refresh presente')
    assert.equal(cookie.httpOnly, true)
    assert.equal(cookie.path, '/api/auth')
  })

  it('ricaricare la pagina mantiene la sessione', async () => {
    await settled(s.page, '/zones')
    await s.page.reload()
    await s.page.waitForLoadState('networkidle')
    assert.doesNotMatch(s.page.url(), /\/auth\/login/)
    await s.page.getByText('Zone', { exact: true }).first().waitFor()
  })

  it('due schede che ricaricano insieme restano entrambe autenticate', async () => {
    const other = await s.context.newPage()
    await settled(s.page, '/zones')
    await settled(other, '/rooms')
    await Promise.all([s.page.reload(), other.reload()])
    await s.page.getByText('Zone', { exact: true }).first().waitFor()
    await other.getByText('Stanze', { exact: true }).first().waitFor()
    assert.doesNotMatch(s.page.url(), /\/auth\/login/)
    assert.doesNotMatch(other.url(), /\/auth\/login/)
    await other.close()
  })

  it('il refresh senza X-Pachi-Auth e rifiutato (403 auth.csrf_rejected)', async () => {
    s.allow(/403/)
    s.allow(/csrf/i)
    const result = await s.page.evaluate(async () => {
      const response = await fetch('/api/auth/refresh-token', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      })
      return { status: response.status, text: await response.text() }
    })
    assert.equal(result.status, 403)
    assert.match(result.text, /auth\.csrf_rejected/)
  })

  it('il logout in una scheda porta l altra al login', async () => {
    const other = await s.context.newPage()
    await settled(other, '/zones')
    await settled(s.page, '/')
    await s.page.getByText('E', { exact: true }).first().click()
    await s.page.getByText(/Disconnetti/i).first().click()
    await s.page.waitForURL(/\/auth\/login/)
    await other.waitForURL(/\/auth\/login/)
    await other.close()
  })

  it('nessun errore di console imprevisto', () => {
    assert.deepEqual(s.errors, [])
  })
})
