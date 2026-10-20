/** Errori di caricamento: testi tradotti (non lo statusText inglese del server). */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { goto, loginOk, openSession, type Session } from '../support/browser.ts'

describe('errori http tradotti', () => {
  let s: Session

  before(async () => {
    s = await openSession()
    await loginOk(s.page)
    s.allow(/Failed to load resource|status of (403|404|409|422|500|503)/)
  })
  after(async () => {
    await s.close()
  })

  const cases: [number, RegExp][] = [
    [403, /Non hai i permessi/],
    [404, /Elemento non trovato/],
    [409, /in conflitto/],
    [422, /non sono validi/],
    [500, /Errore interno/],
    [503, /temporaneamente non disponibile/],
  ]
  for (const [status, text] of cases) {
    it(`la tabella dei mob mostra il testo italiano per ${status}`, async () => {
      await s.page.route(/\/api\/mobs/, (route) => route.fulfill({ status, contentType: 'application/json', body: '{}' }))
      await goto(s.page, '/mobs')
      const banner = s.page.getByTestId('table-error')
      await banner.waitFor()
      assert.match(await banner.innerText(), text)
      await s.page.unroute(/\/api\/mobs/)
    })
  }

  it('rete assente: messaggio dedicato', async () => {
    await s.page.route(/\/api\/mobs/, (route) => route.abort())
    await goto(s.page, '/mobs')
    assert.match(await s.page.getByTestId('table-error').innerText(), /non risponde/)
    await s.page.unroute(/\/api\/mobs/)
  })
})
