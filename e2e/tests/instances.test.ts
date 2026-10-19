/** Istanze vive: elenco, modifica e despawn dalla pagina; tab nel dialog del mob. */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import { confirm, dialog, goto, loginOk, openSession, rawI18nKey, saveDialog, tableRow, type Session } from '../support/browser.ts'

describe('istanze', () => {
  let s: Session
  let api: Api
  let instanceId = 0

  before(async () => {
    api = await Api.connect()
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await s.close()
    if (instanceId) await api.call('DELETE', `/api/instances/mobs/${instanceId}`)
  })

  it('crea un\'istanza (API) e la elenca in pagina', async () => {
    const proto = await api.byVnum('mobs', 1001)
    const room = await api.byVnum('rooms', 1000)
    const created = await api.post('/api/instances/mobs', { prototypeId: proto.id, roomId: room.id, hitPoints: 11 })
    assert.equal(created.status, 201)
    instanceId = created.data.id
    await goto(s.page, '/instances')
    await tableRow(s.page, 'un ratto').first().waitFor()
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('modifica i punti ferita dal dialog', async () => {
    await tableRow(s.page, `#${instanceId}`).or(tableRow(s.page, 'un ratto')).first().dblclick()
    await dialog(s.page).getByLabel('PF massimi').fill('25')
    await dialog(s.page).getByLabel('PF attuali').fill('20')
    await dialog(s.page).getByRole('button', { name: 'Salva' }).click()
    await dialog(s.page).waitFor({ state: 'detached' })
    const got = await api.get(`/api/instances/mobs/${instanceId}`)
    assert.equal(got.data.hitPointsMax, 25)
  })

  it('elimina (despawn) l\'istanza', async () => {
    const deleted = s.page.waitForResponse((r) => r.request().method() === 'DELETE' && /\/api\/instances\/mobs\/\d+/.test(r.url()))
    await tableRow(s.page, 'un ratto').first().locator('.text-negative').click()
    await confirm(s.page)
    await deleted
    assert.equal((await api.get(`/api/instances/mobs/${instanceId}`)).status, 404)
    instanceId = 0
  })

  it('il dialog del mob ha la sezione Istanze vive (mondo che le supporta)', async () => {
    await goto(s.page, '/mobs?zoneId=1')
    const mob = await api.byVnum('mobs', 1000)
    await goto(s.page, `/mobs?zoneId=${mob.zoneId}&mobId=${mob.id}`)
    await dialog(s.page).getByText('Istanze vive').waitFor()
  })

  it('nessun errore di console imprevisto', () => {
    s.allow(/404/)
    assert.deepEqual(s.errors.filter((e) => !/404/.test(e)), [])
    void saveDialog
  })
})
