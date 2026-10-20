/** Mondo pachimud in sola lettura (`pachimud-ro`): istanze, giocatori e razze/classi non offrono azioni di scrittura. */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { goto, loginOk, openSession, tableRow, type Session } from '../support/browser.ts'

describe('pachimud in sola lettura', () => {
  let s: Session

  before(async () => {
    s = await openSession()
    await loginOk(s.page)
    await s.page.getByTestId('world-select').click()
    await Promise.all([
      s.page.waitForNavigation({ waitUntil: 'load' }),
      s.page.locator('.q-menu .q-item', { hasText: 'Pachimud (sola lettura)' }).first().click(),
    ])
    await s.page.getByTestId('world-readonly').waitFor()
  })
  after(async () => {
    await s.close()
  })

  /** Il pulsante con questa etichetta esiste ed e' disabilitato. */
  async function assertDisabled(scope: ReturnType<Session['page']['locator']> | Session['page'], name: string): Promise<void> {
    const button = scope.getByRole('button', { name, exact: true }).first()
    await button.waitFor()
    assert.equal(await button.isDisabled(), true, name)
  }

  it('istanze: "Nuovo mob vivo" e "Nuovo oggetto vivo" disabilitati', async () => {
    await goto(s.page, '/instances')
    await assertDisabled(s.page, 'Nuovo mob vivo')
    await s.page.getByRole('tab', { name: 'Oggetti' }).click()
    await assertDisabled(s.page, 'Nuovo oggetto vivo')
  })

  it('giocatori: nuovo account e azioni di riga disabilitati, ricarica e "Mostra personaggi" no', async () => {
    await goto(s.page, '/players')
    await assertDisabled(s.page, 'Nuovo account')
    const row = tableRow(s.page, 'seed-account')
    await row.waitFor()
    for (const name of ['Modifica email', 'Imposta nuova password', 'Banna', 'Elimina']) await assertDisabled(row, name)
    assert.equal(await row.getByLabel('Mostra personaggi').isDisabled(), false)

    await row.getByLabel('Mostra personaggi').click()
    const character = tableRow(s.page, 'Seedhero')
    await character.waitFor()
    for (const name of ['Modifica', 'Teletrasporta', 'Elimina']) await assertDisabled(character, name)
    assert.equal(await character.getByLabel('Inventario').isDisabled(), false)
    await character.getByLabel('Inventario').click()
    const dialog = s.page.locator('.q-dialog').last()
    await assertDisabled(dialog, 'Aggiungi oggetto')
  })

  it('razze e classi: crea, modifica, disattiva ed elimina disabilitati', async () => {
    for (const [path, create] of [['/content/races', 'Nuova razza'], ['/content/classes', 'Nuova classe']] as const) {
      await goto(s.page, path)
      await assertDisabled(s.page, create)
      const row = s.page.locator('table tbody tr').first()
      await row.waitFor()
      for (const name of ['Modifica', 'Elimina']) await assertDisabled(row, name)
      assert.equal(await row.locator('button[aria-label^="Disattiva"], button[aria-label="Riattiva"]').first().isDisabled(), true)
    }
  })
})
