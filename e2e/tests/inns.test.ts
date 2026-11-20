/** Locande (pachimud): flag `receptionist` nella scheda del mob, elenco con segnalazioni, creazione da template. */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import { goto, loginOk, openSession, rawI18nKey, saveForm, type Session } from '../support/browser.ts'

const MOB_VNUM = 1001 // nessun reset lo carica

describe('locande', () => {
  let s: Session
  let api: Api
  let createdVnum: number | null = null

  /** Toglie il flag dal mob di prova e cancella l'eventuale locandiere creato. */
  async function reset(): Promise<void> {
    const mob = await api.byVnum('mobs', MOB_VNUM)
    if (mob) await api.call('PUT', `/api/mobs/${mob.id}`, { extra: { receptionist: false } })
    if (createdVnum !== null) {
      const made = await api.byVnum('mobs', createdVnum)
      if (made) await api.call('DELETE', `/api/mobs/${made.id}`)
      createdVnum = null
    }
  }

  before(async () => {
    api = await Api.connect()
    await reset()
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await s.close()
    await reset()
  })

  it('un mob diventa locandiere dalla sua scheda, con la spiegazione, e compare nell\'elenco senza stanza', async () => {
    await goto(s.page, `/mobs/${MOB_VNUM}`)
    await s.page.getByText('Locanda', { exact: true }).first().click()
    await s.page.getByTestId('inn-hint').waitFor()
    await s.page.getByTestId('inn-toggle').click()
    await saveForm(s.page)
    const mob = await api.byVnum('mobs', MOB_VNUM)
    assert.equal((await api.call('GET', `/api/mobs/${mob.id}`)).data.extra.receptionist, true)
    assert.equal(await rawI18nKey(s.page), null)

    await goto(s.page, '/inns')
    await s.page.getByTestId('inn-row').first().waitFor()
    await s.page.getByTestId('inn-nospawn-badge').waitFor()
    await s.page.getByTestId('inns-search').fill('zzz-non-esiste')
    await s.page.getByText('Nessuna locanda.').waitFor()
    await s.page.getByTestId('inns-search').fill('ratto')
    await s.page.getByTestId('inn-row').first().click()
    await s.page.waitForURL(new RegExp(`/mobs/${MOB_VNUM}$`))
  })

  it('un locandiere si crea da template e si apre il suo mob', async () => {
    await goto(s.page, '/inns')
    await s.page.getByTestId('inn-create').click()
    await s.page.getByTestId('inn-create-dialog').waitFor()
    await s.page.getByTestId('inn-create-confirm').click()
    await s.page.waitForURL(/\/mobs\/\d+$/)
    createdVnum = Number(s.page.url().split('/').pop())
    const made = await api.byVnum('mobs', createdVnum)
    assert.equal((await api.call('GET', `/api/mobs/${made.id}`)).data.extra.receptionist, true)
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('un locandiere con stanza ha subito il reset di spawn: non compare «senza reset»', async () => {
    await goto(s.page, '/inns')
    await s.page.getByTestId('inn-create').click()
    await s.page.getByTestId('inn-create-room').click()
    await s.page.keyboard.type('Cantina')
    await s.page.locator('.q-menu .q-item', { hasText: '1002' }).first().click()
    await s.page.getByText('Nuovo locandiere da template').click()
    await s.page.getByTestId('inn-create-confirm').click()
    await s.page.waitForURL(/\/mobs\/\d+$/)
    const vnum = Number(s.page.url().split('/').pop())
    const zone = await api.byVnum('zones', 10)
    const script = (await api.call('GET', `/api/zones/${zone.id}/reset-commands`)).data
    assert.ok(script.some((c: { commandType: number; arg1: number; arg3: number }) => c.commandType === 0 && c.arg1 === vnum && c.arg3 === 1002))
    await goto(s.page, '/inns')
    const row = s.page.getByTestId('inn-row').filter({ hasText: String(vnum) })
    await row.waitFor()
    assert.equal(await row.getByTestId('inn-nospawn-badge').count(), 0)
    // ripristino: tolgo il reset e il mob
    await api.call('PUT', `/api/zones/${zone.id}/reset-commands`, {
      commands: script.filter((c: { commandType: number; arg1: number }) => !(c.commandType === 0 && c.arg1 === vnum)).map(
        ({ id: _i, zoneId: _z, orderIndex: _o, extra: _e, ...step }: Record<string, unknown>) => step,
      ),
    })
    const made = await api.byVnum('mobs', vnum)
    if (made) await api.call('DELETE', `/api/mobs/${made.id}`)
  })

  it('nessun errore di console imprevisto', () => {
    assert.deepEqual(s.errors, [])
  })
})
