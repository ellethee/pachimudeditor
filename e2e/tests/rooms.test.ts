/** Stanze: creazione con uscite ed extra description, modifica, clonazione, eliminazione e mappa. */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import {
  addFlag,
  closeDiscarding,
  confirm,
  dismissError,
  dialog,
  goto,
  loginOk,
  openSession,
  rawI18nKey,
  saveDialog,
  tableRow,
  waitDialogsClosed,
  type Session,
} from '../support/browser.ts'

/** Vnum creati dai test (puliti all'avvio e alla fine). */
const VNUMS = [1010, 1011, 1012]

/** Elimina via API le stanze di test rimaste (uscite/extra vanno con la stanza). */
async function cleanup(api: Api): Promise<void> {
  for (const vnum of VNUMS) {
    const room = await api.byVnum('rooms', vnum)
    if (room) await api.call('DELETE', `/api/rooms/${room.id}`)
  }
}

describe('stanze', () => {
  let s: Session
  let api: Api

  before(async () => {
    api = await Api.connect()
    await cleanup(api)
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await s.close()
    await cleanup(api)
  })

  it('la lista mostra le stanze della prima zona', async () => {
    await goto(s.page, '/rooms')
    for (const name of ['Piazza', 'Vicolo', 'Cantina']) await tableRow(s.page, name).waitFor()
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('crea una stanza con flag, uscita ed extra description', async () => {
    await s.page.getByRole('button', { name: 'Nuova stanza' }).click()
    await s.page.getByLabel('Vnum *', { exact: true }).fill('1010')
    await s.page.getByLabel('Nome *').fill('Sala Pw')
    await s.page.getByLabel('Descrizione').fill('Una sala di prova.')
    await addFlag(s.page, 'Flag (digita e invio)', 'DARK')
    await dialog(s.page).locator('.q-chip', { hasText: 'DARK' }).waitFor()
    // uscita a nord verso la Piazza
    const north = dialog(s.page).locator('tr', { hasText: 'Nord' })
    await north.locator('.q-checkbox').first().click()
    await north.locator('.q-select').first().click()
    await s.page.locator('.q-menu .q-item', { hasText: 'Piazza' }).first().click()
    // extra description
    await dialog(s.page).getByRole('button', { name: /Aggiungi extra description/i }).click()
    await dialog(s.page).getByLabel('Parole chiave', { exact: true }).fill('tavolo')
    await dialog(s.page).getByLabel('Testo').fill('Un tavolo di legno.')
    await saveDialog(s.page)
    await waitDialogsClosed(s.page)
    await tableRow(s.page, 'Sala Pw').waitFor()

    const room = await api.byVnum('rooms', 1010)
    const detail = (await api.get(`/api/rooms/${room.id}`)).data
    assert.deepEqual(detail.flags, ['DARK'])
    assert.equal(detail.exits.length, 1)
    assert.equal(detail.exits[0].direction, 0)
    assert.equal(detail.exits[0].targetRoomVnum, 1000)
    assert.deepEqual(
      detail.extraDescriptions.map((e: any) => [e.keywords, e.text]),
      [['tavolo', 'Un tavolo di legno.']],
    )
  })

  it('vnum duplicato: errore tradotto', async () => {
    s.allow(/409/)
    await s.page.getByRole('button', { name: 'Nuova stanza' }).click()
    await s.page.getByLabel('Vnum *', { exact: true }).fill('1000')
    await s.page.getByLabel('Nome *').fill('Doppia')
    await saveDialog(s.page)
    await s.page.locator('.q-notification', { hasText: 'Esiste già una stanza con vnum 1000' }).waitFor()
    assert.equal(await rawI18nKey(s.page), null)
    await closeDiscarding(s.page)
  })

  it('riapre la stanza: chip, uscita ed extra description sono persistiti; la modifica si salva', async () => {
    await tableRow(s.page, 'Sala Pw').locator('.pachi-t2-edit-item').click()
    await dialog(s.page).locator('.q-chip', { hasText: 'DARK' }).waitFor()
    assert.equal(await dialog(s.page).getByLabel('Parole chiave', { exact: true }).inputValue(), 'tavolo')
    await s.page.getByLabel('Nome *').fill('Sala Pw modificata')
    await addFlag(s.page, 'Flag (digita e invio)', 'NO_MOB')
    await saveDialog(s.page)
    await waitDialogsClosed(s.page)
    await tableRow(s.page, 'Sala Pw modificata').waitFor()
    const room = await api.byVnum('rooms', 1010)
    assert.equal(room.name, 'Sala Pw modificata')
    assert.deepEqual(room.flags, ['DARK', 'NO_MOB'])
  })

  it('clona la stanza (extra copiate, uscite no)', async () => {
    await tableRow(s.page, 'Sala Pw modificata').locator('td.q-td button').filter({ hasNot: s.page.locator('.pachi-t2-edit-item') }).first().click()
    await s.page.getByLabel('Nuovo vnum *').fill('1011')
    await s.page.getByLabel('Nuovo nome (opzionale)').fill('Sala clonata')
    await saveDialog(s.page)
    await waitDialogsClosed(s.page)
    await tableRow(s.page, 'Sala clonata').waitFor()
    const clone = await api.byVnum('rooms', 1011)
    const detail = (await api.get(`/api/rooms/${clone.id}`)).data
    assert.equal(detail.exits.length, 0)
    assert.equal(detail.extraDescriptions.length, 1)
  })

  it('eliminare una stanza usata da un reset e rifiutato', async () => {
    s.allow(/409/)
    await tableRow(s.page, 'Piazza').locator('.text-negative').click()
    await s.page.getByText(/referenziata da 2 comandi di reset/).first().waitFor() // avviso preventivo
    await confirm(s.page)
    await s.page.getByText(/Impossibile eliminare: la stanza è referenziata da 2 comandi di reset/).waitFor()
    await dismissError(s.page)
    assert.ok(await api.byVnum('rooms', 1000))
  })

  it('la mappa mostra i nodi della zona', async () => {
    await goto(s.page, '/rooms/map')
    const nodes = s.page.locator('.pachi-room-node')
    await nodes.first().waitFor()
    await s.page.locator('.pachi-room-node', { hasText: 'Piazza' }).waitFor()
    await s.page.locator('.pachi-room-node', { hasText: 'Sala Pw modificata' }).waitFor()
    assert.ok((await nodes.count()) >= 5)
    assert.ok((await s.page.locator('.vue-flow__edge').count()) >= 1)
    assert.equal(await rawI18nKey(s.page), null)
    // un clic su un nodo apre l'editor della stanza
    await s.page.locator('.pachi-room-node', { hasText: 'Vicolo' }).click()
    await dialog(s.page).getByLabel('Nome *').waitFor()
    assert.equal(await dialog(s.page).getByLabel('Nome *').inputValue(), 'Vicolo')
    await s.page.getByLabel('Chiudi').first().click()
    await waitDialogsClosed(s.page)
  })

  it('elimina le stanze create dal test', async () => {
    await goto(s.page, '/rooms')
    for (const name of ['Sala clonata', 'Sala Pw modificata']) {
      await tableRow(s.page, name).locator('.text-negative').click()
      await confirm(s.page)
      await tableRow(s.page, name).waitFor({ state: 'detached' })
    }
    assert.equal(await api.byVnum('rooms', 1010), undefined)
    assert.equal(await api.byVnum('rooms', 1011), undefined)
  })

  it('nessun errore di console imprevisto', () => {
    assert.deepEqual(s.errors, [])
  })
})
