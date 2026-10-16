/** Mob: CRUD dall'interfaccia, flag creati con Invio e persistiti, errori tradotti. */
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
const VNUMS = [1050, 1051]

/** Elimina via API i mob di test rimasti. */
async function cleanup(api: Api): Promise<void> {
  for (const vnum of VNUMS) {
    const mob = await api.byVnum('mobs', vnum)
    if (mob) await api.call('DELETE', `/api/mobs/${mob.id}`)
  }
}

describe('mob', () => {
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

  it('la lista mostra i mob della zona', async () => {
    await goto(s.page, '/mobs')
    await tableRow(s.page, 'una guardia').waitFor()
    await tableRow(s.page, 'un ratto').waitFor()
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('crea un mob con due flag (chip con Invio)', async () => {
    await s.page.getByRole('button', { name: 'Nuovo mob' }).click()
    await s.page.getByLabel('Vnum', { exact: true }).fill('1050')
    await s.page.getByLabel('Parole chiave *').fill('goblin verde')
    await s.page.getByLabel('Descrizione breve *').fill('un goblin verde')
    await s.page.getByLabel('Livello', { exact: true }).fill('7')
    await addFlag(s.page, 'Flag (digita e invio)', 'SENTINEL')
    await addFlag(s.page, 'Flag (digita e invio)', 'AGGRESSIVE')
    await dialog(s.page).locator('.q-chip', { hasText: 'SENTINEL' }).waitFor()
    await dialog(s.page).locator('.q-chip', { hasText: 'AGGRESSIVE' }).waitFor()
    await saveDialog(s.page)
    await waitDialogsClosed(s.page)
    await tableRow(s.page, 'un goblin verde').waitFor()
    const mob = await api.byVnum('mobs', 1050)
    assert.deepEqual(mob.flags, ['SENTINEL', 'AGGRESSIVE'])
    assert.equal(mob.level, 7)
  })

  it('vnum duplicato: errore tradotto', async () => {
    s.allow(/409/)
    await s.page.getByRole('button', { name: 'Nuovo mob' }).click()
    await s.page.getByLabel('Vnum', { exact: true }).fill('1000')
    await s.page.getByLabel('Parole chiave *').fill('x')
    await s.page.getByLabel('Descrizione breve *').fill('doppio')
    await saveDialog(s.page)
    await s.page.locator('.q-notification', { hasText: 'Esiste già un mob con vnum 1000' }).waitFor()
    assert.equal(await rawI18nKey(s.page), null)
    await closeDiscarding(s.page)
  })

  it('modifica: i chip sono ricaricati, se ne aggiunge uno e si salva', async () => {
    await tableRow(s.page, 'un goblin verde').locator('.pachi-t2-edit-item').click()
    await dialog(s.page).locator('.q-chip', { hasText: 'SENTINEL' }).waitFor()
    await dialog(s.page).locator('.q-chip', { hasText: 'AGGRESSIVE' }).waitFor()
    await addFlag(s.page, 'Flag (digita e invio)', 'SCAVENGER')
    await s.page.getByLabel('Descrizione breve *').fill('un goblin rosso')
    await saveDialog(s.page)
    await waitDialogsClosed(s.page)
    await tableRow(s.page, 'un goblin rosso').waitFor()
    const mob = await api.byVnum('mobs', 1050)
    assert.deepEqual(mob.flags, ['SENTINEL', 'AGGRESSIVE', 'SCAVENGER'])
    assert.equal(mob.shortDescription, 'un goblin rosso')
  })

  it('un mob usato da un reset non si elimina (409 tradotto)', async () => {
    s.allow(/409/)
    await tableRow(s.page, 'una guardia').locator('.text-negative').click()
    await confirm(s.page)
    await s.page.getByText(/Impossibile eliminare: il mob è referenziato da 1 comandi di reset/).waitFor()
    await dismissError(s.page)
    assert.ok(await api.byVnum('mobs', 1000))
  })

  it('elimina il mob creato', async () => {
    await tableRow(s.page, 'un goblin rosso').locator('.text-negative').click()
    await confirm(s.page)
    await tableRow(s.page, 'un goblin rosso').waitFor({ state: 'detached' })
    assert.equal(await api.byVnum('mobs', 1050), undefined)
  })

  it('nessun errore di console imprevisto', () => {
    assert.deepEqual(s.errors, [])
  })
})
