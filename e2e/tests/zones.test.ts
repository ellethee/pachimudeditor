/** Zone: lista, creazione, modifica, clonazione, eliminazione ed editor dello script di reset. */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import {
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

/** Vnum usati dai test (puliti all'avvio, per poter rilanciare su uno stack gia' usato). */
const VNUMS = [70, 71, 72, 73, 74]

describe('zone', () => {
  let s: Session
  let api: Api

  before(async () => {
    api = await Api.connect()
    for (const vnum of VNUMS) {
      const zone = await api.byVnum('zones', vnum)
      if (zone) await api.call('DELETE', `/api/zones/${zone.id}`)
    }
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await s.close()
    for (const vnum of VNUMS) {
      const zone = await api.byVnum('zones', vnum)
      if (zone) await api.call('DELETE', `/api/zones/${zone.id}`)
    }
  })

  it('la lista mostra le zone seminate', async () => {
    await goto(s.page, '/zones')
    await tableRow(s.page, 'Zona Alfa').waitFor()
    await tableRow(s.page, 'Zona Vuota').waitFor()
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('crea una zona', async () => {
    await s.page.getByRole('button', { name: 'Nuova zona' }).click()
    await s.page.getByLabel('Vnum *', { exact: true }).fill('70')
    await s.page.getByLabel('Nome *').fill('Zona Pw')
    await s.page.getByLabel('Builder').fill('playwright')
    await s.page.getByLabel('Vnum minimo *').fill('7000')
    await s.page.getByLabel('Vnum massimo *').fill('7099')
    await saveDialog(s.page)
    await waitDialogsClosed(s.page)
    await tableRow(s.page, 'Zona Pw').waitFor()
    const zone = await api.byVnum('zones', 70)
    assert.equal(zone.builder, 'playwright')
    assert.equal(zone.bottomVnum, 7000)
  })

  it('vnum duplicato: errore tradotto, il dialog resta aperto', async () => {
    s.allow(/409/)
    await s.page.getByRole('button', { name: 'Nuova zona' }).click()
    await s.page.getByLabel('Vnum *', { exact: true }).fill('10')
    await s.page.getByLabel('Nome *').fill('Duplicata')
    await saveDialog(s.page)
    await s.page.locator('.q-notification', { hasText: 'Esiste già una zona con vnum 10' }).waitFor()
    assert.equal(await s.page.locator('.q-dialog').count(), 1)
    assert.equal(await rawI18nKey(s.page), null)
    await closeDiscarding(s.page)
  })

  it('range incoerente: errore di validazione, niente creazione', async () => {
    await s.page.getByRole('button', { name: 'Nuova zona' }).click()
    await s.page.getByLabel('Vnum *', { exact: true }).fill('71')
    await s.page.getByLabel('Nome *').fill('Range storto')
    await s.page.getByLabel('Vnum minimo *').fill('5000')
    await s.page.getByLabel('Vnum massimo *').fill('10')
    await saveDialog(s.page)
    await s.page.locator('.q-notification', { hasText: 'Il vnum minimo non può superare il vnum massimo' }).waitFor()
    assert.equal(await api.byVnum('zones', 71), undefined)
    await closeDiscarding(s.page)
  })

  it('modifica una zona', async () => {
    await tableRow(s.page, 'Zona Pw').locator('.pachi-t2-edit-item').click()
    await s.page.getByLabel('Nome *').fill('Zona Pw rinominata')
    await saveDialog(s.page)
    await waitDialogsClosed(s.page)
    await tableRow(s.page, 'Zona Pw rinominata').waitFor()
    assert.equal((await api.byVnum('zones', 70)).name, 'Zona Pw rinominata')
  })

  it('clona una zona copiando lo script di reset', async () => {
    const source = await api.byVnum('zones', 70)
    await api.call('PUT', `/api/zones/${source.id}/reset-commands`, {
      commands: [{ commandType: 0, arg1: 1001, arg2: 1, arg3: 1002, arg4: 1 }],
    })
    await tableRow(s.page, 'Zona Pw rinominata').locator('td.q-td.text-right button').nth(1).click()
    await s.page.getByLabel('Nuovo vnum *').fill('72')
    await s.page.getByLabel('Nuovo nome *').fill('Zona clonata')
    await dialog(s.page).getByText('Copia anche lo script di reset').click()
    await saveDialog(s.page)
    await waitDialogsClosed(s.page)
    await tableRow(s.page, 'Zona clonata').waitFor()
    const clone = await api.byVnum('zones', 72)
    const commands = (await api.get(`/api/zones/${clone.id}/reset-commands`)).data
    assert.equal(commands.length, 1)
  })

  it('eliminare una zona non vuota e rifiutato (409 tradotto)', async () => {
    s.allow(/409/)
    await tableRow(s.page, 'Zona Alfa').locator('.text-negative').click()
    await confirm(s.page)
    await s.page.getByText(/contiene ancora 3 stanze, 2 mob e 2 oggetti/).waitFor()
    assert.equal(await rawI18nKey(s.page), null)
    await dismissError(s.page)
    assert.ok(await api.byVnum('zones', 10))
  })

  it('elimina le zone vuote create dal test', async () => {
    for (const name of ['Zona clonata', 'Zona Pw rinominata']) {
      await tableRow(s.page, name).locator('.text-negative').click()
      await confirm(s.page)
      await tableRow(s.page, name).waitFor({ state: 'detached' })
    }
    assert.equal(await api.byVnum('zones', 70), undefined)
    assert.equal(await api.byVnum('zones', 72), undefined)
  })

  it('editor reset: aggiunge un passo, salva, ricarica e lo ritrova', async () => {
    const created = await api.post('/api/zones', {
      vnum: 73, name: 'Zona reset', builder: 'pw', bottomVnum: 7300, topVnum: 7399,
    })
    assert.equal(created.status, 201)
    await goto(s.page, `/zones/${created.data.id}/resets`)
    await s.page.getByText('Nessun passo di reset per questa zona.').waitFor()
    await s.page.getByRole('button', { name: 'Aggiungi passo' }).click()
    await s.page.getByLabel('Vnum mob').fill('1001')
    await s.page.getByLabel('Max esistenti').fill('2')
    await s.page.getByLabel('Vnum stanza').fill('1002')
    await s.page.getByText('un ratto').waitFor() // risoluzione del nome via lookup
    await s.page.getByRole('button', { name: 'Salva script' }).click()
    await s.page.locator('.q-notification', { hasText: 'Script di reset salvato.' }).waitFor()
    const saved = (await api.get(`/api/zones/${created.data.id}/reset-commands`)).data
    assert.deepEqual(
      saved.map((c: any) => [c.commandType, c.arg1, c.arg2, c.arg3]),
      [[0, 1001, 2, 1002]],
    )
    await s.page.reload()
    await s.page.getByText(/Carica mob — vnum 1001/).waitFor()
    assert.equal(await s.page.getByLabel('Vnum mob').inputValue(), '1001')
    // eliminare il passo e salvare svuota lo script
    await s.page.locator('.pachi-zone-reset-item .text-negative').first().click()
    await s.page.getByRole('button', { name: 'Salva script' }).click()
    await s.page.locator('.q-notification', { hasText: 'Script di reset salvato.' }).first().waitFor()
    assert.deepEqual((await api.get(`/api/zones/${created.data.id}/reset-commands`)).data, [])
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('nessun errore di console imprevisto', () => {
    assert.deepEqual(s.errors, [])
  })
})
