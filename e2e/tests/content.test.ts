/** Contenuti (razze/classi YAML) su una copia temporanea delle definizioni di esempio (vedi support/stack.ts). */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import { dialog, goto, loginOk, openSession, rawI18nKey, saveDialog, tableRow, waitDialogsClosed, type Session } from '../support/browser.ts'

describe('contenuti', () => {
  let s: Session
  let api: Api

  before(async () => {
    api = await Api.connect()
    await api.call('DELETE', '/api/content/races/pwrace')
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await s.close()
    await api.call('DELETE', '/api/content/races/pwrace')
  })

  it('elenca razze e classi', async () => {
    await goto(s.page, '/content/races')
    await tableRow(s.page, 'human').first().waitFor()
    assert.equal(await rawI18nKey(s.page), null)
    await goto(s.page, '/content/classes')
    await tableRow(s.page, 'warrior').first().waitFor()
  })

  it('crea, modifica ed elimina una razza (copia temporanea)', async () => {
    await goto(s.page, '/content/races')
    await s.page.getByRole('button', { name: 'Nuova razza' }).click()
    await dialog(s.page).getByLabel('Id', { exact: false }).first().fill('pwrace')
    await dialog(s.page).getByLabel('Nome', { exact: false }).first().fill('Pw Razza')
    await dialog(s.page).getByLabel('Descrizione', { exact: false }).first().fill('Razza di prova')
    await saveDialog(s.page)
    await waitDialogsClosed(s.page)
    await tableRow(s.page, 'Pw Razza').waitFor()
    assert.equal((await api.get('/api/content/races/pwrace')).data.name, 'Pw Razza')

    await tableRow(s.page, 'Pw Razza').getByRole('button').first().click()
    await dialog(s.page).getByLabel('Descrizione', { exact: false }).first().fill('Razza modificata')
    await saveDialog(s.page)
    await waitDialogsClosed(s.page)
    assert.equal((await api.get('/api/content/races/pwrace')).data.description, 'Razza modificata')

    await tableRow(s.page, 'Pw Razza').locator('.text-negative').click()
    await s.page.locator('.q-dialog').last().getByRole('button', { name: 'Elimina', exact: true }).click()
    await tableRow(s.page, 'Pw Razza').waitFor({ state: 'detached' })
  })

  it('nessun errore di console imprevisto', () => {
    assert.deepEqual(s.errors, [])
  })
})
