/**
 * Giocatori dei mondi su file sul mondo Diku Modificato: lettura (pagina guidata dal descrittore, avviso, dettaglio a sezioni, inventario,
 * password mai mostrata, voce di menu solo con la capability) e scrittura (mondo scrivibile `dikumod-rw`: modifica dei campi, server acceso,
 * conflitto, inventario aggiungi/sposta/togli; mondo in sola lettura senza controlli di modifica). I giocatori sono SINTETICI (vedi `tests/support/dikumod_players.py`,
 * scritti dallo stack nelle copie di lavoro); se `E2E_DIKUMOD` non e' impostata la suite si salta.
 */
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
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

  it('mondo in sola lettura: nessun controllo di modifica nel dettaglio e scritture 409', async () => {
    await goto(s.page, '/player-files')
    await s.page.getByTestId('player-open-tizio').click()
    const d = dialog(s.page)
    await d.getByTestId('player-readonly-note').waitFor()
    assert.equal(await d.getByTestId('edit-start').count(), 0)
    await d.getByRole('tab', { name: 'Inventario' }).click()
    await d.getByTestId('inventory-table').waitFor()
    assert.equal(await d.getByTestId('inventory-add').count(), 0)
    assert.equal(await d.getByTestId('inventory-remove-0').count(), 0)
    await s.page.keyboard.press('Escape')
    await waitDialogsClosed(s.page)
    const ro = (await Api.connect()).inWorld('dikumod')
    for (const [method, path] of [['PATCH', ''], ['POST', '/inventory/items'], ['PATCH', '/inventory/items/0'], ['DELETE', '/inventory/items/0']] as const) {
      const response = await ro.call(method, `/api/world/players/tizio${path}`, { vnum: 1, wearSlot: null })
      assert.equal(response.status, 409, `${method} ${path}`)
      assert.equal(response.body.detail[0].code, 'world.read_only')
    }
  })

  it('API scrittura: PATCH, valori non validi, conflitto, copia .bak e password intatta', async () => {
    const rw = (await Api.connect()).inWorld('dikumod-rw')
    const before = (await rw.get('/api/world/players/caio')).data
    const patched = await rw.call('PATCH', '/api/world/players/caio', { revision: before.revision, details: { gold: 321, title: 'Provato' } })
    assert.equal(patched.status, 200)
    assert.equal(patched.data.gold, 321)
    assert.equal(patched.data.details.title, 'Provato')
    assert.doesNotMatch(JSON.stringify(patched.body), /SYNTH-PW9/)
    const stale = await rw.call('PATCH', '/api/world/players/caio', { revision: before.revision, details: { gold: 5 } })
    assert.equal(stale.status, 409)
    assert.equal(stale.body.detail[0].code, 'worldplayers.conflict')
    const bad = await rw.call('PATCH', '/api/world/players/caio', { details: { str: 999, password: 'x' } })
    assert.equal(bad.status, 422)
    assert.equal(bad.body.detail[0].code, 'worldplayers.invalid_value')
    assert.equal((await rw.call('PATCH', '/api/world/players/x%5Cy', { details: {} })).status, 404)
    assert.equal((await rw.call('PATCH', '/api/world/players/nessuno', { details: {} })).status, 404)
    assert.equal((await rw.get('/api/world/players/caio')).data.gold, 321)
    const lib = process.env.E2E_DIKUMOD_RW_LIB
    if (lib) {
      assert.ok(existsSync(join(lib, 'players', '.caio.dat.bak')))
      const file = readFileSync(join(lib, 'players', 'caio.dat'))
      assert.equal(file.subarray(2974, 2974 + 9).toString('latin1'), 'SYNTH-PW9') // la password non e' mai cambiata
    }
  })

  it('mondo scrivibile: modifica dal dettaglio (campi, salvataggio, conflitto) e rilettura', async () => {
    await goto(s.page, '/')
    await pickWorld(s, 'Diku Modificato (scrivibile)')
    await goto(s.page, '/player-files')
    await s.page.getByTestId('player-open-tizio').click()
    const d = dialog(s.page)
    await d.getByTestId('player-write-note').waitFor()
    await d.getByTestId('edit-start').click()
    await d.getByTestId('edit-title').fill('il Temerario')
    await d.getByTestId('edit-gold').fill('4321')
    await d.getByTestId('edit-str').fill('999') // fuori intervallo: rifiutato dal server, si resta in modifica
    await d.getByTestId('edit-save').click()
    await d.locator('.q-banner.bg-negative').first().waitFor()
    assert.match(await d.locator('.q-banner.bg-negative').first().innerText(), /str/)
    await d.getByTestId('edit-str').fill('17')
    await d.getByTestId('edit-save').click()
    await d.getByTestId('edit-start').waitFor()
    assert.match(await d.getByTestId('field-title').innerText(), /il Temerario/)
    assert.match(await d.getByTestId('field-gold').innerText(), /4[.,]?321/)
    assert.match(await d.getByTestId('field-str').innerText(), /17/)
    assert.equal(await rawI18nKey(s.page), null)
    await s.page.keyboard.press('Escape')
    await waitDialogsClosed(s.page)
    await tableRow(s.page, 'Tizio').getByText(/4[.,]?321/).waitFor() // l'elenco si ricarica alla chiusura
    // conflitto: il file cambia dopo l'apertura del dettaglio
    await s.page.getByTestId('player-open-tizio').click()
    const c = dialog(s.page)
    await c.getByTestId('edit-start').click()
    await c.getByTestId('edit-title').fill('Perso')
    const rw = (await Api.connect()).inWorld('dikumod-rw')
    assert.equal((await rw.call('PATCH', '/api/world/players/tizio', { details: { hit: 150 } })).status, 200)
    await c.getByTestId('edit-save').click()
    await c.locator('.q-banner.bg-negative').first().waitFor()
    assert.match(await c.locator('.q-banner.bg-negative').first().innerText(), /cambiat|changed/i)
    assert.match(await c.getByTestId('field-title').innerText(), /il Temerario/) // nessuna scrittura
    await s.page.keyboard.press('Escape')
    await waitDialogsClosed(s.page)
  })

  it('mondo scrivibile: inventario, aggiungi (ricerca per nome), cambia slot, togli', async () => {
    await s.page.getByTestId('player-open-sempronio').click()
    const d = dialog(s.page)
    await d.getByRole('tab', { name: 'Inventario' }).click()
    await d.getByTestId('inventory-add').click()
    await d.getByTestId('inventory-pick').fill('spada')
    await s.page.locator('.q-menu .q-item', { hasText: /spada/i }).first().click()
    await d.getByTestId('inventory-add-confirm').click()
    await d.getByTestId('inventory-table').getByText(/spada/i).first().waitFor()
    const rw = (await Api.connect()).inWorld('dikumod-rw')
    let inv = (await rw.get('/api/world/players/sempronio/inventory')).data
    assert.equal(inv.items.length, 1)
    assert.equal(inv.items[0].wearSlot, null)
    assert.equal(inv.problem, null)
    await d.getByTestId('inventory-slot-0').click()
    await s.page.locator('.q-menu .q-item', { hasText: 'Impugnato' }).first().click()
    await d.getByTestId('inventory-table').getByText('Impugnato').waitFor()
    inv = (await rw.get('/api/world/players/sempronio/inventory')).data
    assert.equal(inv.items[0].wearSlot, 'wield')
    await d.getByTestId('inventory-remove-0').click()
    await s.page.locator('.q-dialog').last().getByRole('button', { name: 'Togli', exact: true }).click()
    await d.getByText('Nessun oggetto').waitFor()
    inv = (await rw.get('/api/world/players/sempronio/inventory')).data
    assert.equal(inv.items.length, 0)
    assert.equal(await rawI18nKey(s.page), null)
    await s.page.keyboard.press('Escape')
    await waitDialogsClosed(s.page)
  })

  it('server acceso: avviso con conferma obbligatoria prima di scrivere', async () => {
    const lib = process.env.E2E_DIKUMOD_RW_LIB
    if (!lib) return // senza il percorso della copia (E2E_SKIP_STACK) non si puo' simulare il server
    const code = "import socket,time; s=socket.socket(); s.bind(('127.0.0.1',0)); s.listen(); print('up',flush=True); time.sleep(120)"
    const child = spawn('python3', ['-c', code], { cwd: lib, stdio: ['ignore', 'pipe', 'inherit'] })
    try {
      await new Promise<void>((resolve) => child.stdout!.once('data', () => resolve()))
      const rw = (await Api.connect()).inWorld('dikumod-rw')
      assert.equal((await rw.get('/api/world/players/status')).data.serverRunning, true)
      const refused = await rw.call('PATCH', '/api/world/players/mevio', { details: { gold: 9 } })
      assert.equal(refused.status, 409)
      assert.equal(refused.body.detail[0].code, 'worldplayers.server_running')
      await goto(s.page, '/player-files')
      await s.page.getByTestId('player-open-mevio').click()
      const d = dialog(s.page)
      await d.getByTestId('player-server-running').waitFor()
      await d.getByTestId('edit-start').click()
      await d.getByTestId('edit-gold').fill('9')
      assert.equal(await d.getByTestId('edit-save').isDisabled(), true) // senza conferma non si salva
      await d.getByTestId('confirm-server').click()
      await d.getByTestId('edit-save').click()
      await d.getByTestId('edit-start').waitFor()
      assert.equal((await rw.get('/api/world/players/mevio')).data.gold, 9)
      await s.page.keyboard.press('Escape')
      await waitDialogsClosed(s.page)
    } finally {
      child.kill()
    }
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
    assert.deepEqual(s.errors.filter((e) => !/\b(409|422)\b/.test(e)), []) // solo gli errori voluti (valore non valido, conflitto)
  })
})
