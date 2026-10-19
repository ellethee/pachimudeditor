/** Giocatori: account (crea, banna, elimina) e personaggi (elenco; seminati dal setup). */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import { confirm, goto, loginOk, openSession, rawI18nKey, tableRow, waitDialogsClosed, type Session } from '../support/browser.ts'

/** Compila il prompt di Quasar Dialog (input + OK). */
async function answer(s: Session, value: string): Promise<void> {
  const box = s.page.locator('.q-dialog').last()
  await box.locator('input').fill(value)
  await box.getByRole('button', { name: 'OK', exact: true }).click()
}

describe('giocatori', () => {
  let s: Session
  let api: Api

  before(async () => {
    api = await Api.connect()
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await s.close()
    const created = (await api.list('players/accounts')).find((a: { username: string }) => a.username === 'pw-account')
    if (created) await api.call('DELETE', `/api/players/accounts/${created.id}?cascade=true`)
  })

  it('crea un account con i tre prompt', async () => {
    await goto(s.page, '/players')
    await tableRow(s.page, 'seed-account').waitFor()
    await s.page.getByRole('button', { name: 'Nuovo account' }).click()
    await answer(s, 'pw-account')
    await answer(s, 'Password-di-prova-1')
    await answer(s, 'pw@example.com')
    await tableRow(s.page, 'pw-account').waitFor()
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('banna e riabilita l\'account', async () => {
    const row = tableRow(s.page, 'pw-account')
    await row.getByLabel('Banna').click()
    await row.getByText('Bannato').waitFor()
    await row.getByLabel('Rimuovi il ban').click()
    await row.getByText('Attivo').waitFor()
  })

  it('personaggi: l\'elenco mostra il personaggio seminato', async () => {
    await tableRow(s.page, 'seed-account').getByLabel('Mostra personaggi').click()
    await tableRow(s.page, 'Seedhero').waitFor()
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('elimina l\'account creato', async () => {
    await s.page.getByRole('tab', { name: 'Account' }).click()
    await tableRow(s.page, 'pw-account').getByLabel('Elimina').click()
    await confirm(s.page)
    await tableRow(s.page, 'pw-account').waitFor({ state: 'detached' })
  })

  it('un account con personaggi non si elimina senza cascata', async () => {
    // l'account ha personaggi e la cascata non e' spuntata: la UI chiude il dialog senza inviare nessun DELETE
    const sent: string[] = []
    const track = (r: { method(): string; url(): string }): void => {
      if (r.method() === 'DELETE') sent.push(r.url())
    }
    s.page.on('request', track)
    await tableRow(s.page, 'seed-account').getByLabel('Elimina').click()
    await confirm(s.page)
    await waitDialogsClosed(s.page)
    s.page.off('request', track)
    assert.deepEqual(sent, [])
    assert.ok((await api.list('players/accounts')).some((a: { username: string }) => a.username === 'seed-account'))
  })

  it('nessun errore di console imprevisto', () => {
    assert.deepEqual(s.errors, [])
  })
})
