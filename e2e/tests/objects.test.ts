/** Oggetti: CRUD dall'interfaccia, flag (extra e wear) creati con Invio e persistiti, errori tradotti. */
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

/** Vnum creati dai test. */
const VNUMS = [1060, 1061]

/** Elimina via API gli oggetti di test rimasti. */
async function cleanup(api: Api): Promise<void> {
  for (const vnum of VNUMS) {
    const obj = await api.byVnum('objects', vnum)
    if (obj) await api.call('DELETE', `/api/objects/${obj.id}`)
  }
}

describe('oggetti', () => {
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

  it('la lista mostra gli oggetti della zona', async () => {
    await goto(s.page, '/objects')
    await tableRow(s.page, 'una spada').waitFor()
    await tableRow(s.page, 'un sasso').waitFor()
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('crea un oggetto con extra e wear flag (chip con Invio)', async () => {
    await s.page.getByRole('button', { name: 'Nuovo oggetto' }).click()
    await s.page.getByLabel('Vnum', { exact: true }).fill('1060')
    await s.page.getByLabel('Parole chiave *').fill('elmo ferro')
    await s.page.getByLabel('Descrizione breve *').fill('un elmo di ferro')
    await s.page.getByLabel('Peso').fill('7')
    await addFlag(s.page, 'Extra flag (digita e invio)', 'GLOW')
    await addFlag(s.page, 'Extra flag (digita e invio)', 'MAGIC')
    await addFlag(s.page, 'Wear flag (digita e invio)', 'HEAD')
    await dialog(s.page).locator('.q-chip', { hasText: 'GLOW' }).waitFor()
    await dialog(s.page).locator('.q-chip', { hasText: 'MAGIC' }).waitFor()
    await dialog(s.page).locator('.q-chip', { hasText: 'HEAD' }).waitFor()
    await saveDialog(s.page)
    await waitDialogsClosed(s.page)
    await tableRow(s.page, 'un elmo di ferro').waitFor()
    const obj = await api.byVnum('objects', 1060)
    assert.deepEqual(obj.extraFlags, ['GLOW', 'MAGIC'])
    assert.deepEqual(obj.wearFlags, ['HEAD'])
    assert.equal(obj.weight, 7)
  })

  it('vnum duplicato: errore tradotto', async () => {
    s.allow(/409/)
    await s.page.getByRole('button', { name: 'Nuovo oggetto' }).click()
    await s.page.getByLabel('Vnum', { exact: true }).fill('1000')
    await s.page.getByLabel('Parole chiave *').fill('x')
    await s.page.getByLabel('Descrizione breve *').fill('doppio')
    await saveDialog(s.page)
    await s.page.locator('.q-notification', { hasText: 'Esiste già un oggetto con vnum 1000' }).waitFor()
    assert.equal(await rawI18nKey(s.page), null)
    await closeDiscarding(s.page)
  })

  it('modifica: i chip sono ricaricati, se ne aggiunge uno e si salva', async () => {
    await tableRow(s.page, 'un elmo di ferro').locator('.pachi-t2-edit-item').click()
    await dialog(s.page).locator('.q-chip', { hasText: 'GLOW' }).waitFor()
    await dialog(s.page).locator('.q-chip', { hasText: 'HEAD' }).waitFor()
    await addFlag(s.page, 'Wear flag (digita e invio)', 'WIELD')
    await s.page.getByLabel('Descrizione breve *').fill('un elmo di bronzo')
    await saveDialog(s.page)
    await waitDialogsClosed(s.page)
    await tableRow(s.page, 'un elmo di bronzo').waitFor()
    const obj = await api.byVnum('objects', 1060)
    assert.deepEqual(obj.extraFlags, ['GLOW', 'MAGIC'])
    assert.deepEqual(obj.wearFlags, ['HEAD', 'WIELD'])
    assert.equal(obj.shortDescription, 'un elmo di bronzo')
  })

  it('un oggetto usato da un reset non si elimina (409 tradotto)', async () => {
    s.allow(/409/)
    await tableRow(s.page, 'una spada').locator('.text-negative').click()
    await confirm(s.page)
    await s.page.getByText(/Impossibile eliminare: l'oggetto è referenziato da 1 comandi di reset/).waitFor()
    await dismissError(s.page)
    assert.ok(await api.byVnum('objects', 1000))
  })

  it("elimina l'oggetto creato", async () => {
    await tableRow(s.page, 'un elmo di bronzo').locator('.text-negative').click()
    await confirm(s.page)
    await tableRow(s.page, 'un elmo di bronzo').waitFor({ state: 'detached' })
    assert.equal(await api.byVnum('objects', 1060), undefined)
  })

  it('nessun errore di console imprevisto', () => {
    assert.deepEqual(s.errors, [])
  })
})
