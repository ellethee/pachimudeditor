/**
 * Canale live del mondo pachimud (finto server `livectl` con il profilo pachimud, mondo `pachimud-live`): capability dal `hello`, letture,
 * `zone.reload` e `instances.list` via API, pulsante «Ricarica nel gioco» nel dettaglio zona (solo con il comando dichiarato) e sua assenza
 * nel mondo senza canale.
 */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import { goto, loginOk, openSession, type Session } from '../support/browser.ts'

/** Sceglie un mondo dal selettore nella barra (ricarica la pagina). */
async function pickWorld(s: Session, name: string): Promise<void> {
  await s.page.getByTestId('world-select').click()
  await Promise.all([
    s.page.waitForNavigation({ waitUntil: 'load' }),
    s.page.locator('.q-menu .q-item', { hasText: name }).first().click(),
  ])
}

describe('canale live (pachimud)', () => {
  let s: Session

  before(async () => {
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await s.close()
  })

  it('API: stato dal hello, letture di pachimud, reload e istanze', async () => {
    const live = (await Api.connect()).inWorld('pachimud-live')
    const status = (await live.get('/api/world/live/status')).data
    assert.equal(status.state, 'connected')
    assert.equal(status.mud.kind, 'pachimud')
    assert.ok(status.commands.includes('zone.reload') && !status.commands.includes('player.set'))
    const who = (await live.get('/api/world/live/who')).data.players as { name: string; race: string }[]
    assert.equal(who.find((p) => p.name === 'Tester')?.race, 'human')
    const reload = (await live.post('/api/world/live/zones/reload', { vnum: 10 })).data
    assert.equal(reload.reloaded, true)
    assert.equal(reload.name, 'Zona Alfa')
    const inst = (await live.get('/api/world/live/instances?roomVnum=1001')).data
    assert.equal(inst.count, 3)
    assert.equal((await live.get('/api/world/live/instances?zoneVnum=10')).data.count, 4)
    assert.equal((await live.post('/api/world/live/zones/reload', { vnum: 999 })).status, 404)
    assert.equal((await live.post('/api/world/live/echo', { text: 'x', all: true })).status, 409) // il gioco non ha `echo`
    assert.equal((await (await Api.connect()).inWorld('pachimud-ro').post('/api/world/live/zones/reload', { vnum: 10 })).status, 409)
  })

  it('UI: «Ricarica nel gioco» nel dettaglio zona, solo con il canale', async () => {
    await pickWorld(s, 'Pachimud (live)')
    await goto(s.page, '/zones/10')
    await s.page.getByTestId('zone-live-reload').click()
    await s.page.getByTestId('zone-live-instances').getByText('2 mob e 2 oggetti').waitFor()
    await s.page.locator('.q-notification', { hasText: 'Zona Zona Alfa ricaricata nel gioco' }).waitFor()
    await pickWorld(s, 'Pachimud')
    await goto(s.page, '/zones/10')
    await s.page.getByRole('heading', { name: /Zona Alfa/ }).waitFor()
    assert.equal(await s.page.getByTestId('zone-live-reload').count(), 0)
    assert.equal(await s.page.getByTestId('zone-live-instances').count(), 0)
  })
  it('UI: «Ricarica la zona nel gioco» in /inns, solo con il canale', async () => {
    const live = (await Api.connect()).inWorld('pachimud-live')
    const mob = (await live.byVnum('mobs', 1000))!
    await live.call('PUT', `/api/mobs/${mob.id}`, { extra: { receptionist: true } })
    try {
      await pickWorld(s, 'Pachimud (live)')
      await goto(s.page, '/inns')
      await s.page.getByTestId('inn-reload-zone').first().click()
      await s.page.locator('.q-notification', { hasText: 'Zona Zona Alfa ricaricata nel gioco' }).waitFor()
      await pickWorld(s, 'Pachimud')
      await goto(s.page, '/inns')
      await s.page.getByTestId('inns-table').waitFor()
      assert.equal(await s.page.getByTestId('inn-reload-zone').count(), 0)
    } finally {
      await live.call('PUT', `/api/mobs/${mob.id}`, { extra: { receptionist: false } })
    }
  })
})
