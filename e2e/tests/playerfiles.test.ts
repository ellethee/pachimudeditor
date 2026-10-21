/**
 * Giocatori dei mondi su file (sola lettura) sul mondo Diku Modificato: pagina guidata dal descrittore, avviso, dettaglio a sezioni,
 * inventario, password mai mostrata, voce di menu solo con la capability. I giocatori sono SINTETICI (vedi `tests/support/dikumod_players.py`,
 * scritti dallo stack nelle copie di lavoro); se `E2E_DIKUMOD` non e' impostata la suite si salta.
 */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import { HAS_DIKUMOD } from '../support/stack.ts'
import { dialog, goto, loginOk, openSession, rawI18nKey, tableRow, waitDialogsClosed, type Session } from '../support/browser.ts'

/** Sceglie un mondo dal selettore nella barra (ricarica la pagina). */
async function pickWorld(s: Session, name: string): Promise<void> {
  await s.page.getByTestId('world-select').click()
  await Promise.all([
    s.page.waitForNavigation({ waitUntil: 'load' }),
    s.page.locator('.q-menu .q-item', { hasText: name }).first().click(),
  ])
}

describe('giocatori su file (dikumod)', { skip: HAS_DIKUMOD ? false : 'E2E_DIKUMOD non impostata' }, () => {
  let s: Session

  before(async () => {
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await s.close()
  })

  it('API: capability, elenco, dettaglio e nessuna password; pachimud risponde 409', async () => {
    const api = await Api.connect()
    const ro = api.inWorld('dikumod')
    const worlds = (await api.get('/api/worlds')).data as { id: string; capabilities: Record<string, boolean> }[]
    assert.equal(worlds.find((w) => w.id === 'dikumod')!.capabilities.supportsPlayerRecords, true)
    assert.equal(worlds.find((w) => w.id === 'pachimud')!.capabilities.supportsPlayerRecords, false)
    const list = await ro.get('/api/world/players?pageSize=100')
    assert.deepEqual(
      (list.data.items as { id: string }[]).map((p) => p.id),
      ['caio', 'mevio', 'sempronio', 'tizio'],
    )
    const detail = await ro.get('/api/world/players/tizio')
    const inventory = await ro.get('/api/world/players/tizio/inventory')
    for (const response of [list, detail, inventory]) assert.doesNotMatch(JSON.stringify(response.data), /SYNTH-PW9|"password"|"pwd"/i)
    assert.equal(inventory.data.items.length, 3)
    assert.equal((await api.get('/api/world/players')).status, 409)
  })

  it('il menu mostra Giocatori (file) solo nel mondo con la capability', async () => {
    await goto(s.page, '/')
    await pickWorld(s, 'Diku Modificato (sola lettura)')
    await s.page.getByTestId('world-readonly').waitFor()
    const tile = s.page.locator('.pachi-hub-dash__grid').getByText('Giocatori', { exact: true })
    await tile.first().waitFor()
    assert.equal(await tile.count(), 1)
    await tile.first().click()
    await s.page.waitForURL(/\/player-files$/)
  })

  it('elenco: banner di avviso, colonne dichiarate, ricerca e ordinamento', async () => {
    await goto(s.page, '/player-files')
    await s.page.getByTestId('players-warning').waitFor()
    assert.match(await s.page.getByTestId('players-warning').innerText(), /server di gioco potrebbe essere in esecuzione/)
    const table = s.page.getByTestId('players-table')
    await tableRow(s.page, 'Tizio').waitFor()
    for (const label of ['Nome', 'Livello', 'Classe', 'Razza', 'Monete', 'Ultimo accesso', 'Tempo di gioco']) {
      await table.getByRole('columnheader', { name: new RegExp(label) }).waitFor()
    }
    const row = tableRow(s.page, 'Tizio')
    assert.match(await row.innerText(), /Warrior/)
    assert.match(await row.innerText(), /Human/)
    assert.match(await tableRow(s.page, 'Caio').innerText(), /Warrior \/ Thief/)
    assert.equal(await tableRow(s.page, 'Sempronio').getByText('No', { exact: true }).count(), 1) // senza password
    await s.page.getByTestId('players-search').fill('zio')
    await tableRow(s.page, 'Tizio').waitFor()
    await tableRow(s.page, 'Caio').waitFor({ state: 'detached' })
    await s.page.getByTestId('players-search').fill('')
    await tableRow(s.page, 'Caio').waitFor()
    await table.getByRole('columnheader', { name: /Livello/ }).click()
    await s.page.locator('table tbody tr').first().filter({ hasText: /Sempronio|Tizio|Mevio/ }).waitFor() // livello crescente: Caio (31) per ultimo
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('dettaglio: sezioni, tabelle, inventario con slot e annidamento; sola lettura, password assente', async () => {
    await s.page.getByTestId('player-open-tizio').click()
    const d = dialog(s.page)
    await d.getByTestId('player-detail').waitFor()
    await d.getByTestId('player-readonly-note').waitFor()
    for (const section of ['general', 'abilities', 'points', 'state']) await d.getByTestId(`section-${section}`).waitFor()
    assert.match(await d.getByTestId('field-title').innerText(), /il Prode/)
    assert.match(await d.getByTestId('field-str').innerText(), /16/)
    assert.match(await d.getByTestId('player-summary').innerText(), /password impostata/)
    await d.getByRole('tab', { name: 'Abilità ed effetti' }).click()
    await d.getByTestId('list-skills').waitFor()
    await d.getByRole('tab', { name: 'Inventario' }).click()
    const inventory = d.getByTestId('inventory-table')
    await inventory.getByText('Un gile in pelle').waitFor()
    assert.match(await inventory.locator('tbody tr').first().innerText(), /Corpo/)
    await inventory.getByText('prototipo sconosciuto').waitFor()
    assert.doesNotMatch(await d.innerText(), /SYNTH-PW9/)
    assert.equal(await rawI18nKey(s.page), null)
    // Escape chiude il dialog
    await s.page.keyboard.press('Escape')
    await waitDialogsClosed(s.page)
  })

  it('problemi: owner del rent diverso e giocatore senza rent', async () => {
    await s.page.getByTestId('player-open-mevio').click()
    const d = dialog(s.page)
    await d.getByRole('tab', { name: 'Inventario' }).click()
    await d.getByTestId('inventory-problem').waitFor()
    assert.match(await d.getByTestId('inventory-problem').innerText(), /proprietario/)
    await s.page.keyboard.press('Escape')
    await waitDialogsClosed(s.page)
    await s.page.getByTestId('player-open-sempronio').click()
    await dialog(s.page).getByRole('tab', { name: 'Inventario' }).click()
    await dialog(s.page).getByText('Nessun oggetto').waitFor()
    await s.page.keyboard.press('Escape')
    await waitDialogsClosed(s.page)
  })

  it('la pagina dei giocatori di pachimud non cambia e /player-files vi e\' inaccessibile', async () => {
    await pickWorld(s, 'Pachimud')
    await goto(s.page, '/player-files')
    await s.page.locator('.pachi-hub-dash__grid').waitFor()
    assert.equal(new URL(s.page.url()).pathname, '/')
    await goto(s.page, '/players')
    await tableRow(s.page, 'seed-account').waitFor()
  })

  it('nessun errore di console', async () => {
    assert.deepEqual(s.errors, [])
  })
})
