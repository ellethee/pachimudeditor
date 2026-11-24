/** Bacheche e posta (pachimud, sola lettura): elenco, messaggi con ricerca e conteggio della posta senza testi (seminati dal setup). */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import { confirm, goto, loginOk, openSession, rawI18nKey, type Session } from '../support/browser.ts'

/** Sceglie un mondo dal selettore nella barra (ricarica la pagina). */
async function pickWorld(s: Session, name: string): Promise<void> {
  await s.page.getByTestId('world-select').click()
  await Promise.all([
    s.page.waitForNavigation({ waitUntil: 'load' }),
    s.page.locator('.q-menu .q-item', { hasText: name }).first().click(),
  ])
}

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
    assert.match(await s.page.getByTestId('board-message').first().innerText(), /20\d\d/) // la data c'e'
    await s.page.getByTestId('board-message').first().click()
    assert.match(await s.page.getByTestId('board-message-text').first().innerText(), /spada quasi nuova/)
    await s.page.getByTestId('board-search').fill('drago')
    await s.page.waitForFunction(() => document.querySelectorAll('[data-testid="board-message"]').length === 1)
    assert.match(await s.page.getByTestId('board-message').first().innerText(), /Cerco gruppo/)
    assert.equal(await rawI18nKey(s.page), null)
    await s.page.getByTestId('board-back').click()
    await s.page.getByTestId('boards-table').waitFor()
  })

  it('senza canale live non si cancella: niente pulsanti, nota di sola lettura', async () => {
    await goto(s.page, '/boards')
    await s.page.getByTestId('board-row').filter({ hasText: 'piazza' }).click()
    await s.page.getByTestId('board-message').first().waitFor()
    assert.equal(await s.page.getByTestId('board-delete').count(), 0)
    assert.equal(await s.page.getByTestId('board-clear').count(), 0)
    assert.match(await s.page.getByTestId('board-moderation-note').innerText(), /Sola lettura/)
  })

  it('con il canale live cancella un messaggio e svuota la bacheca solo con conferma, passando dal gioco', async () => {
    await pickWorld(s, 'Pachimud (live)')
    await goto(s.page, '/boards')
    await s.page.getByTestId('board-row').filter({ hasText: 'piazza' }).click()
    await s.page.getByTestId('board-message').first().waitFor()
    assert.match(await s.page.getByTestId('board-message').first().innerText(), /\b1\b/)
    await s.page.getByTestId('board-delete').first().click()
    await s.page.locator('.q-dialog', { hasText: 'Cancellare il messaggio?' }).waitFor()
    await s.page.locator('.q-dialog').last().locator('button').first().click() // annulla (il primo pulsante): niente cancellato
    await s.page.locator('.q-dialog').first().waitFor({ state: 'detached' })
    const live = (await Api.connect()).inWorld('pachimud-live')
    assert.equal((await live.get('/api/world/live/status')).data.commands.includes('board.delete'), true)
    await s.page.getByTestId('board-delete').first().click()
    await confirm(s.page)
    await s.page.locator('.q-notification', { hasText: 'Messaggio cancellato' }).waitFor()
    assert.equal((await live.call('DELETE', '/api/world/live/boards/piazza/messages/1')).status, 404) // il gioco l'aveva gia' tolto (id riga)
    await s.page.getByTestId('board-clear').click()
    await confirm(s.page)
    await s.page.locator('.q-notification', { hasText: 'messaggi cancellati' }).waitFor()
    assert.equal(await rawI18nKey(s.page), null)
    assert.equal((await (await Api.connect()).inWorld('pachimud-ro').call('DELETE', '/api/world/live/boards/piazza')).status, 409)
  })

  it('la posta mostra solo i conteggi, mai il testo', async () => {
    await goto(s.page, '/boards')
    await s.page.getByTestId('boards-tab-mail').click()
    await s.page.getByTestId('mail-table').getByText('aldo').waitFor() // la tabella compare prima dei dati
    assert.match(await s.page.getByTestId('mail-total').innerText(), /3/)
    const text = await s.page.getByTestId('mail-table').innerText()
    assert.match(text, /aldo/)
    assert.match(text, /bea/)
    assert.doesNotMatch(await s.page.locator('body').innerText(), /SEGRETO/)
    assert.equal(await rawI18nKey(s.page), null)
  })
})
