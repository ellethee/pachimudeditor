/** Selettore di mondo: secondo mondo basedmud (copia temporanea di area/), capability, sola lettura, extra. */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import { HAS_DIKUMOD } from '../support/stack.ts'
import { dialog, goto, loginOk, openSession, rawI18nKey, saveDialog, tableRow, waitDialogsClosed, type Session } from '../support/browser.ts'

/** Sceglie un mondo dal selettore nella barra (ricarica la pagina). */
async function pickWorld(s: Session, name: string): Promise<void> {
  await s.page.getByTestId('world-select').click()
  await Promise.all([
    s.page.waitForNavigation({ waitUntil: 'load' }),
    s.page.locator('.q-menu .q-item', { hasText: name }).first().click(),
  ])
}

describe('mondi', () => {
  let s: Session
  let api: Api

  before(async () => {
    api = (await Api.connect()).inWorld('basedmud')
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await s.close()
  })

  it('/api/worlds elenca i mondi con le capability', async () => {
    const worlds = (await (await Api.connect()).get('/api/worlds')).data as { id: string; capabilities: Record<string, boolean> }[]
    assert.deepEqual(worlds.map((w) => w.id), ['pachimud', 'basedmud', 'basedmud-ro', 'pachimud-ro', ...(HAS_DIKUMOD ? ['dikumod', 'dikumod-rw'] : [])])
    assert.equal(worlds[1]!.capabilities.supportsPlayers, false)
    assert.equal(worlds[2]!.capabilities.readOnly, true)
  })

  it('pachimud: la dashboard mostra tutte le funzioni e il selettore elenca i mondi', async () => {
    await goto(s.page, '/')
    await s.page.getByTestId('world-select').waitFor()
    for (const title of ['Panoramica', 'Giocatori', 'Istanze', 'Trasferimento zone', 'Razze']) {
      await s.page.locator('.pachi-hub-dash__grid').getByText(title, { exact: true }).first().waitFor()
    }
    assert.equal(await s.page.getByTestId('world-readonly').count(), 0)
  })

  it('basedmud: cambia mondo dal selettore, il menu nasconde le funzioni non supportate', async () => {
    await pickWorld(s, 'BasedMud')
    await s.page.getByTestId('world-select').waitFor()
    await s.page.locator('.pachi-hub-dash__grid').getByText('Zone', { exact: true }).first().waitFor()
    for (const title of ['Panoramica', 'Giocatori', 'Istanze', 'Trasferimento zone', 'Razze', 'Classi']) {
      assert.equal(await s.page.locator('.pachi-hub-dash__grid').getByText(title, { exact: true }).count(), 0, title)
    }
    // la scelta e' ricordata: dopo un ricaricamento il mondo resta basedmud
    await s.page.reload()
    await s.page.getByTestId('world-select').waitFor()
    assert.match(await s.page.locator('.pachi-world-select .q-field__native').innerText(), /BasedMud/)
  })

  it('basedmud: le route non supportate rimandano alla dashboard', async () => {
    await goto(s.page, '/players')
    await s.page.locator('.pachi-hub-dash__grid').waitFor()
    assert.equal(new URL(s.page.url()).pathname, '/')
  })

  it('basedmud: elenca le zone (anche con id negativo) e apre la zona negativa', async () => {
    await goto(s.page, '/zones')
    await tableRow(s.page, 'Smurfville').waitFor()
    await tableRow(s.page, 'protype').waitFor()
    await goto(s.page, '/zones?zoneId=-49')
    await dialog(s.page).getByLabel('Nome *').waitFor()
    assert.equal(await dialog(s.page).getByLabel('Nome *').inputValue(), 'protype')
    // la sezione "campi specifici del mondo" e' presente e il range originale e' in sola lettura
    await dialog(s.page).getByText('Campi specifici del mondo').click()
    assert.equal(await dialog(s.page).getByLabel('Range vnum originale').isDisabled(), true)
    await s.page.getByLabel('Chiudi').first().click()
    await waitDialogsClosed(s.page)
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('basedmud: modifica un mob (deep-link mobId) e i campi extra, con enum ROM', async () => {
    await goto(s.page, '/mobs?zoneId=3000&mobId=3000')
    await dialog(s.page).getByLabel('Descrizione breve *').waitFor()
    // niente campi non supportati editabili
    assert.equal(await dialog(s.page).getByLabel('Esperienza').isDisabled(), true)
    // flag con elenco ROM
    await dialog(s.page).locator('.q-chip', { hasText: 'sentinel' }).waitFor()
    await dialog(s.page).getByText('Campi specifici del mondo').click()
    await dialog(s.page).getByLabel('Materiale').fill('mithril')
    await dialog(s.page).getByLabel('Descrizione breve *').fill('il mago anziano')
    await saveDialog(s.page)
    await waitDialogsClosed(s.page)
    await tableRow(s.page, 'il mago anziano').waitFor()
    const mob = (await api.get('/api/mobs/3000')).data
    assert.equal(mob.shortDescription, 'il mago anziano')
    assert.equal(mob.extra.material, 'mithril')
    assert.deepEqual(mob.extra.shop.buyTypes.length > 0, true)
    // la query e' stata ripulita: un ricaricamento non riapre il dialog
    assert.equal(new URL(s.page.url()).searchParams.has('mobId'), false)
  })

  it('basedmud: deep-link objectId e mappa stanze con zoneId', async () => {
    const obj = (await api.get('/api/objects?pageSize=1&zoneId=3000')).data.items[0]
    await goto(s.page, `/objects?zoneId=${obj.zoneId}&objectId=${obj.id}`)
    await dialog(s.page).getByLabel('Descrizione breve *').waitFor()
    await s.page.getByLabel('Chiudi').first().click()
    await waitDialogsClosed(s.page)
    await goto(s.page, '/rooms/map?zoneId=3000')
    // regressione: la zona del deep-link, non quella di default, e' quella mostrata (caricamenti sovrapposti)
    const graph = (await api.get('/api/rooms/graph?zoneId=3000')).data as { nodes: unknown[] }
    await s.page.locator('.vue-flow__node').first().waitFor()
    await s.page.waitForFunction((n) => document.querySelectorAll('.vue-flow__node').length === n, graph.nodes.length)
  })

  it('basedmud sola lettura: badge, niente pulsanti di scrittura, scrittura rifiutata', async () => {
    await pickWorld(s, 'sola lettura')
    await s.page.getByTestId('world-readonly').waitFor()
    await goto(s.page, '/mobs?zoneId=3000')
    await tableRow(s.page, 'il mago anziano').waitFor()
    assert.equal(await s.page.getByRole('button', { name: 'Nuovo mob' }).count(), 0)
    const ro = (await Api.connect()).inWorld('basedmud-ro')
    assert.equal((await ro.call('PUT', '/api/mobs/3000', { level: 3 })).status, 409)
  })

  it('torna a pachimud: nessun errore di console e nessuna X-World stantia', async () => {
    await pickWorld(s, 'Pachimud')
    await goto(s.page, '/mobs')
    await tableRow(s.page, 'una guardia').waitFor()
    s.allow(/409/)
    assert.deepEqual(s.errors.filter((e) => !/409/.test(e)), [])
  })
})
