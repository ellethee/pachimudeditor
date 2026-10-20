/** Header di sicurezza: la SPA (con CSP stretta) e /docs (Swagger UI da jsDelivr) funzionano davvero nel browser, senza violazioni CSP. */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { BASE_URL, goto, loginOk, openSession, type Session } from '../support/browser.ts'

describe('header di sicurezza', () => {
  let s: Session
  const violations: string[] = []

  before(async () => {
    s = await openSession()
    await s.page.exposeFunction('reportCsp', (text: string) => void violations.push(text))
    await s.page.addInitScript(() => {
      document.addEventListener('securitypolicyviolation', (e) => void (window as unknown as { reportCsp: (t: string) => void }).reportCsp(`${e.violatedDirective} ${e.blockedURI}`))
    })
  })
  after(async () => {
    await s.close()
  })

  it('le risposte portano gli header attesi', async () => {
    const response = await fetch(`${BASE_URL}/`)
    assert.equal(response.headers.get('x-content-type-options'), 'nosniff')
    assert.equal(response.headers.get('x-frame-options'), 'DENY')
    assert.equal(response.headers.get('referrer-policy'), 'no-referrer')
    assert.match(response.headers.get('content-security-policy') ?? '', /script-src 'self'; /)
  })

  it('SPA: login, dashboard e mappa stanze funzionano con la CSP', async () => {
    await loginOk(s.page)
    await goto(s.page, '/rooms/map')
    await s.page.locator('.vue-flow__node').first().waitFor()
    await goto(s.page, '/zones')
    await s.page.locator('.q-table, table').first().waitFor()
    assert.deepEqual(violations, [])
    assert.deepEqual(s.errors, [])
  })

  it('/docs: Swagger UI si carica ed elenca le operazioni', async () => {
    await goto(s.page, '/docs')
    await s.page.locator('.swagger-ui .opblock').first().waitFor({ timeout: 30_000 })
    assert.deepEqual(violations, [])
    assert.deepEqual(s.errors, [])
  })
})
