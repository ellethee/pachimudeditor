/** Controllo trasversale: ogni pagina si carica senza chiavi i18n grezze ne' errori di console. */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import { goto, loginOk, openSession, rawI18nKey, type Session } from '../support/browser.ts'

describe('pagine: i18n e console', () => {
  let s: Session

  before(async () => {
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await s.close()
  })

  for (const [path, marker] of [
    ['/', 'Overview'],
    ['/zones', 'Nuova zona'],
    ['/rooms', 'Nuova stanza'],
    ['/rooms/map', 'Mappa stanze'],
    ['/mobs', 'Nuovo mob'],
    ['/objects', 'Nuovo oggetto'],
  ] as const) {
    it(`${path} senza chiavi grezze`, async () => {
      await goto(s.page, path)
      await s.page.getByText(marker).first().waitFor()
      await s.page.waitForLoadState('networkidle')
      assert.equal(await rawI18nKey(s.page), null)
    })
  }

  it('/zones/:id/resets senza chiavi grezze', async () => {
    const api = await Api.connect()
    const zone = await api.byVnum('zones', 10)
    await goto(s.page, `/zones/${zone.id}/resets`)
    await s.page.getByText('Script di reset').first().waitFor()
    await s.page.getByText(/Carica mob — vnum 1000/).waitFor()
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('nessun errore di console', () => {
    assert.deepEqual(s.errors, [])
  })
})
