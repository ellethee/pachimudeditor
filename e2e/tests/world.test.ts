/** Panoramica del mondo, ricerca globale e grafo tra zone (mondo pachimud). */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { dialog, goto, loginOk, openSession, rawI18nKey, waitDialogsClosed, type Session } from '../support/browser.ts'

describe('mondo: panoramica, ricerca, grafo', () => {
  let s: Session

  before(async () => {
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await s.close()
  })

  it('panoramica: contatori e tabella delle zone', async () => {
    await goto(s.page, '/world')
    await s.page.locator('table tbody tr', { hasText: 'Zona Alfa' }).waitFor()
    await s.page.locator('table tbody tr', { hasText: 'Zona Vuota' }).waitFor()
    await s.page.getByText('Qualità dei dati').waitFor()
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('panoramica: il link della zona apre davvero l\'editor della zona', async () => {
    await s.page.locator('table tbody tr', { hasText: 'Zona Alfa' }).getByRole('link', { name: 'Zona Alfa' }).click()
    await dialog(s.page).getByLabel('Nome *').waitFor()
    assert.equal(await dialog(s.page).getByLabel('Nome *').inputValue(), 'Zona Alfa')
    await s.page.getByLabel('Chiudi').first().click()
    await waitDialogsClosed(s.page)
  })

  it('ricerca: trova un mob e il risultato apre l\'editor del mob', async () => {
    await goto(s.page, '/world/search?q=guardia')
    const hit = s.page.locator('.q-item', { hasText: 'una guardia' })
    await hit.waitFor()
    await hit.click()
    await dialog(s.page).getByLabel('Descrizione breve *').waitFor()
    assert.equal(await dialog(s.page).getByLabel('Descrizione breve *').inputValue(), 'una guardia')
    await s.page.getByLabel('Chiudi').first().click()
    await waitDialogsClosed(s.page)
  })

  it('ricerca: un oggetto apre l\'editor dell\'oggetto', async () => {
    await goto(s.page, '/world/search?q=spada')
    await s.page.locator('.q-item', { hasText: 'una spada' }).click()
    await dialog(s.page).getByLabel('Descrizione breve *').waitFor()
    await s.page.getByLabel('Chiudi').first().click()
    await waitDialogsClosed(s.page)
  })

  it('grafo tra zone: nodi e senza chiavi grezze', async () => {
    await goto(s.page, '/world/graph')
    await s.page.locator('.vue-flow__node').first().waitFor()
    assert.ok((await s.page.locator('.vue-flow__node').count()) >= 1)
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('nessun errore di console imprevisto', () => {
    assert.deepEqual(s.errors, [])
  })
})
