/** Bacheche e posta (pachimud, sola lettura): elenco, messaggi con ricerca e conteggio della posta senza testi (seminati dal setup). */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { goto, loginOk, openSession, rawI18nKey, type Session } from '../support/browser.ts'

describe('bacheche', () => {
  let s: Session

  before(async () => {
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await s.close()
  })

  it('elenca le bacheche, mostra i messaggi e li cerca', async () => {
    await goto(s.page, '/boards')
    const row = s.page.getByTestId('board-row').filter({ hasText: 'piazza' })
    await row.waitFor()
    assert.match(await row.innerText(), /senza oggetto/)
    assert.match(await row.innerText(), /\b2\b/)
    await row.click()
    await s.page.getByTestId('board-message').first().waitFor()
    assert.equal(await s.page.getByTestId('board-message').count(), 2)
    await s.page.getByTestId('board-message').first().click()
    assert.match(await s.page.getByTestId('board-message-text').first().innerText(), /spada quasi nuova/)
    await s.page.getByTestId('board-search').fill('drago')
    await s.page.waitForFunction(() => document.querySelectorAll('[data-testid="board-message"]').length === 1)
    assert.match(await s.page.getByTestId('board-message').first().innerText(), /Cerco gruppo/)
    assert.equal(await rawI18nKey(s.page), null)
    await s.page.getByTestId('board-back').click()
    await s.page.getByTestId('boards-table').waitFor()
  })

  it('la posta mostra solo i conteggi, mai il testo', async () => {
    await goto(s.page, '/boards')
    await s.page.getByTestId('boards-tab-mail').click()
    await s.page.getByTestId('mail-table').waitFor()
    assert.match(await s.page.getByTestId('mail-total').innerText(), /3/)
    const text = await s.page.getByTestId('mail-table').innerText()
    assert.match(text, /aldo/)
    assert.match(text, /bea/)
    assert.doesNotMatch(await s.page.locator('body').innerText(), /SEGRETO/)
    assert.equal(await rawI18nKey(s.page), null)
  })
})
