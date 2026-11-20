/** Mappa stanze: pannelli, collegamento trascinando le maniglie, porta, eliminazione uscita, nuova stanza collegata, layout salvato. */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import { goto, loginOk, openSession, pickOption, rawI18nKey, type Session } from '../support/browser.ts'

/** Vnum creati dai test (puliti all'avvio e alla fine). */
const VNUMS = [1080, 1081, 1082]

/** Etichetta della porta chiudibile nelle select. */
const DOOR_CLOSABLE = /chiudibile|closable/i

/** Elimina via API le stanze di test rimaste (uscite comprese). */
async function cleanup(api: Api): Promise<void> {
  for (const vnum of VNUMS) {
    const room = await api.byVnum('rooms', vnum)
    if (room) await api.call('DELETE', `/api/rooms/${room.id}`)
  }
}

describe('mappa stanze', () => {
  let s: Session
  let api: Api
  let zoneId: number
  const ids: Record<number, number> = {}

  /** Uscite di una stanza via API. */
  async function exitsOf(vnum: number): Promise<any[]> {
    return (await api.call('GET', `/api/rooms/${ids[vnum]}`)).data.exits
  }

  /** Trascina dalla maniglia di uscita `out-<dir>` di una stanza alla maniglia di ingresso `in-<dir>` di un'altra. */
  async function drag(from: string, out: string, to: string, inn: string): Promise<void> {
    const source = s.page.locator('.vue-flow__node', { hasText: from }).locator(`[data-handleid="${out}"]`)
    const target = s.page.locator('.vue-flow__node', { hasText: to }).locator(`[data-handleid="${inn}"]`)
    const a = (await source.boundingBox())!
    const b = (await target.boundingBox())!
    await s.page.mouse.move(a.x + a.width / 2, a.y + a.height / 2)
    await s.page.mouse.down()
    await s.page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 12 })
    await s.page.mouse.up()
  }

  /** Clic sull'arco di un'uscita (l'id vue-flow è `e<id>`). */
  async function clickEdge(exitId: number): Promise<void> {
    await s.page.locator(`.vue-flow__edge[data-id="e${exitId}"] path`).first().click({ force: true })
  }

  before(async () => {
    api = await Api.connect()
    await cleanup(api)
    zoneId = (await api.byVnum('zones', 10)).id
    for (const [vnum, name] of [[1080, 'Mappa nord'], [1081, 'Mappa sud']] as const) {
      const res = await api.call('POST', '/api/rooms', { vnum, zoneId, name })
      assert.equal(res.status, 201)
      ids[vnum] = res.data.id
    }
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await s.close()
    await cleanup(api)
  })

  it('un clic su una stanza apre il pannello e “Apri scheda” porta all’editor; la legenda si apre', async () => {
    await goto(s.page, `/rooms/map?zoneId=${zoneId}`)
    await s.page.locator('.pachi-room-node', { hasText: 'Mappa nord' }).click()
    await s.page.getByTestId('map-room-panel').getByText('#1080').waitFor()
    await s.page.getByRole('button', { name: 'Legenda' }).click()
    await s.page.getByTestId('map-legend').waitFor()
    assert.equal(await rawI18nKey(s.page), null)
    await s.page.getByTestId('map-open-room').click()
    await s.page.waitForURL(/\/rooms(\/\d+|\?.*roomId=)/)
  })

  it('la ricerca evidenzia la stanza', async () => {
    await goto(s.page, `/rooms/map?zoneId=${zoneId}`)
    await s.page.locator('.pachi-room-node').first().waitFor()
    await s.page.getByTestId('map-search').click()
    await s.page.keyboard.type('Mappa sud')
    await s.page.locator('.q-menu .q-item', { hasText: 'Mappa sud' }).click()
    await s.page.locator('.pachi-room-node--highlight', { hasText: 'Mappa sud' }).waitFor()
  })

  it('trascinando tra due maniglie si crea l’uscita con il ritorno', async () => {
    await goto(s.page, `/rooms/map?zoneId=${zoneId}`)
    await s.page.locator('.pachi-room-node', { hasText: 'Mappa nord' }).waitFor()
    await drag('Mappa nord', 'out-2', 'Mappa sud', 'in-0')
    await s.page.getByTestId('room-link-dialog').waitFor()
    await s.page.getByTestId('room-link-save').click()
    await s.page.getByTestId('room-link-dialog').waitFor({ state: 'detached' })
    assert.deepEqual((await exitsOf(1080)).map((e) => [e.direction, e.targetRoomId]), [[2, ids[1081]]])
    assert.deepEqual((await exitsOf(1081)).map((e) => [e.direction, e.targetRoomId]), [[0, ids[1080]]])
    await s.page.locator('.vue-flow__edge').first().waitFor()
  })

  it('il pannello dell’arco cambia la porta su entrambi i sensi', async () => {
    await goto(s.page, `/rooms/map?zoneId=${zoneId}`)
    await s.page.locator('.pachi-room-node', { hasText: 'Mappa nord' }).waitFor()
    await clickEdge((await exitsOf(1080))[0].id)
    await s.page.getByTestId('map-edge-panel').waitFor()
    await pickOption(s.page, 'Porta', DOOR_CLOSABLE)
    await s.page.getByTestId('map-save-door').click()
    await s.page.locator('.q-notification', { hasText: 'Porta aggiornata' }).waitFor()
    assert.equal((await exitsOf(1080))[0].doorFlag, 1)
    assert.equal((await exitsOf(1081))[0].doorFlag, 1)
  })

  it('elimina andata e ritorno dal pannello dell’arco', async () => {
    await goto(s.page, `/rooms/map?zoneId=${zoneId}`)
    await s.page.locator('.pachi-room-node', { hasText: 'Mappa nord' }).waitFor()
    await clickEdge((await exitsOf(1080))[0].id)
    await s.page.getByRole('button', { name: 'Elimina andata e ritorno' }).click()
    await s.page.locator('.q-dialog').getByRole('button', { name: 'OK' }).click()
    await s.page.getByTestId('map-edge-panel').waitFor({ state: 'detached' })
    assert.equal((await exitsOf(1080)).length, 0)
    assert.equal((await exitsOf(1081)).length, 0)
  })

  it('nuova stanza collegata dal pannello', async () => {
    await goto(s.page, `/rooms/map?zoneId=${zoneId}`)
    await s.page.locator('.pachi-room-node', { hasText: 'Mappa nord' }).click()
    await s.page.getByRole('button', { name: 'Nuova stanza collegata' }).click()
    await s.page.getByTestId('new-room-name').fill('Mappa nuova')
    await s.page.getByTestId('new-room-save').click()
    await s.page.locator('.pachi-room-node', { hasText: 'Mappa nuova' }).waitFor()
    const target = (await api.call('GET', `/api/rooms/${(await exitsOf(1080))[0].targetRoomId}`)).data
    assert.equal(target.name, 'Mappa nuova')
    VNUMS.push(target.vnum) // pulito da cleanup
  })

  it('il layout trascinato resta salvato e “Reset layout” lo cancella', async () => {
    await goto(s.page, `/rooms/map?zoneId=${zoneId}`)
    const node = s.page.locator('.pachi-room-node', { hasText: 'Mappa sud' })
    await node.waitFor()
    const before = (await node.boundingBox())!
    await s.page.mouse.move(before.x + 20, before.y + 8)
    await s.page.mouse.down()
    await s.page.mouse.move(before.x + 140, before.y + 90, { steps: 8 })
    await s.page.mouse.up()
    await goto(s.page, `/rooms/map?zoneId=${zoneId}`)
    const moved = (await s.page.locator('.pachi-room-node', { hasText: 'Mappa sud' }).boundingBox())!
    await s.page.getByTestId('map-reset-layout').click()
    await s.page.waitForTimeout(800)
    const reset = (await s.page.locator('.pachi-room-node', { hasText: 'Mappa sud' }).boundingBox())!
    assert.ok(Math.abs(moved.x - reset.x) > 5 || Math.abs(moved.y - reset.y) > 5, 'il reset deve riportare il nodo al layout del server')
  })
})
