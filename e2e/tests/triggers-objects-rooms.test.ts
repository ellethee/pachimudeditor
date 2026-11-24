/**
 * Script degli oggetti (`extra.scripts`) e trigger delle stanze (`extra.triggers`) di pachimud: schede nei form, salvataggio, 422 per tipi non
 * ammessi, problemi del controllo sulla riga giusta e click dalla pagina Controllo che apre la voce. Il finto server riporta i problemi scritti
 * in `<socket>.issues.json`.
 */
import assert from 'node:assert/strict'
import { rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import { goto, loginOk, openSession, rawI18nKey, saveForm, type Session } from '../support/browser.ts'

const ISSUES = (): string => join(process.env.E2E_LIVE_SOCKET_DIR!, 'live-pachimud.sock.issues.json')
const OBJ_VNUM = 1001
const ROOM_VNUM = 1002
const WORLD = 'pachimud-live'
const FILE = (name: string): string => `/gioco/definitions/zones/ZonaAlfa/${name}.yaml`

describe('script degli oggetti e trigger delle stanze', () => {
  let s: Session
  let api: Api

  /** Toglie script e trigger dalle voci di prova. */
  async function reset(): Promise<void> {
    const obj = await api.byVnum('objects', OBJ_VNUM)
    if (obj) await api.call('PUT', `/api/objects/${obj.id}`, { extra: { scripts: [] } })
    const room = await api.byVnum('rooms', ROOM_VNUM)
    if (room) await api.call('PUT', `/api/rooms/${room.id}`, { extra: { triggers: [] } })
  }

  before(async () => {
    api = (await Api.connect()).inWorld(WORLD)
    await reset()
    s = await openSession()
    await loginOk(s.page)
    await s.page.getByTestId('world-select').click()
    await Promise.all([s.page.waitForNavigation({ waitUntil: 'load' }), s.page.locator('.q-menu .q-item', { hasText: 'Pachimud (live)' }).first().click()])
  })
  after(async () => {
    rmSync(ISSUES(), { force: true })
    await s.close()
    await reset()
  })

  it('uno script dell\'oggetto si aggiunge dalla scheda Script e si salva; il comando non ammesso avvisa', async () => {
    await goto(s.page, `/objects/${OBJ_VNUM}`)
    await s.page.getByText('Script', { exact: true }).first().click()
    await s.page.getByTestId('trigger-add').click()
    const actions = s.page.getByTestId('trigger-actions')
    await actions.getByTestId('action-text').first().fill('say ciao')
    await s.page.getByText('solo mpecho, mpechoat e mpechoaround').waitFor()
    await actions.getByTestId('action-text').first().fill('mpechoat $n Senti un brivido.')
    await actions.getByTestId('if-add').last().click()
    await actions.getByTestId('cond-level').fill('< 5')
    await actions.getByTestId('if-then').first().getByTestId('action-text').first().fill('mpecho Un lampo!')
    await saveForm(s.page)
    const obj = await api.byVnum('objects', OBJ_VNUM)
    const saved = (await api.call('GET', `/api/objects/${obj.id}`)).data.extra.scripts
    assert.equal(saved[0].type, 'get')
    assert.equal(saved[0].actions[1].if.level, '< 5')
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('un trigger della stanza si aggiunge e si salva; i tipi dei mob sono 422', async () => {
    await goto(s.page, `/rooms/${ROOM_VNUM}`)
    await s.page.getByText('Trigger', { exact: true }).first().click()
    await s.page.getByTestId('trigger-add').click()
    await s.page.getByTestId('trigger-actions').getByTestId('action-text').first().fill('mpecho Un soffio gelido.')
    await saveForm(s.page)
    const room = await api.byVnum('rooms', ROOM_VNUM)
    const saved = (await api.call('GET', `/api/rooms/${room.id}`)).data.extra.triggers
    assert.deepEqual(saved.map((t: { type: string }) => t.type), ['enter'])
    const bad = await api.call('PUT', `/api/rooms/${room.id}`, { extra: { triggers: [{ type: 'death', actions: ['mpecho x'] }] } })
    assert.equal(bad.status, 422)
    assert.equal(JSON.stringify(bad.body).includes('pachimud.invalid_choice'), true)
  })

  it('fase 3: random per oggetti e stanze si salva, un comando MP e\' 422', async () => {
    const obj = await api.byVnum('objects', OBJ_VNUM)
    const ok = await api.call('PUT', `/api/objects/${obj.id}`, { extra: { scripts: [{ type: 'random', chance: 5, actions: ['mpecho Brilla.'] }] } })
    assert.equal(ok.status, 200)
    const bad = await api.call('PUT', `/api/objects/${obj.id}`, { extra: { scripts: [{ type: 'get', actions: ['mpkill $n'] }] } })
    assert.equal(bad.status, 422)
    assert.equal(JSON.stringify(bad.body).includes('mpkill'), true)
    const room = await api.byVnum('rooms', ROOM_VNUM)
    const r = await api.call('PUT', `/api/rooms/${room.id}`, { extra: { triggers: [{ type: 'random', actions: ['mpecho Un fruscio.'] }] } })
    assert.equal(r.status, 200)
    await reset()
  })

  it('i problemi del controllo compaiono sulla riga giusta e il click apre la voce', async () => {
    const obj = await api.byVnum('objects', OBJ_VNUM)
    await api.call('PUT', `/api/objects/${obj.id}`, {
      extra: { scripts: [{ type: 'get', actions: ['mpecho ok'] }, { type: 'wear', actions: ['say ciao'] }] },
    })
    const room = await api.byVnum('rooms', ROOM_VNUM)
    await api.call('PUT', `/api/rooms/${room.id}`, { extra: { triggers: [{ type: 'enter', actions: [{ if: { who: 'i' }, then: ['mpecho x'] }] }] } })
    const objLine = await lineOf('objects', 'say ciao')
    const roomLine = await lineOf('rooms', 'who: i')
    writeFileSync(
      ISSUES(),
      JSON.stringify([
        { severity: 'error', code: 'trigger-command-unknown', message: "object 1001, trigger 1: il comando 'say' non e' ammesso", file: FILE('objects'), line: objLine },
        { severity: 'error', code: 'trigger-condition-invalid', message: "room 1002, trigger 0: 'who: i' vale solo per i mob", file: FILE('rooms'), line: roomLine },
        { severity: 'error', code: 'trigger-type-not-allowed', message: "room 1002, trigger 0: il tipo 'get' non vale per un room", file: FILE('rooms'), line: roomLine },
      ])
    )
    await goto(s.page, '/content/check')
    await s.page.getByTestId('check-run').click()
    await s.page.getByTestId('content-problem').first().waitFor()
    await s.page.getByText('Il tipo di un trigger non vale per chi lo possiede', { exact: false }).first().waitFor()
    await s.page.getByTestId('content-problem').filter({ hasText: "il comando 'say'" }).click()
    await s.page.waitForURL(new RegExp(`/objects/${OBJ_VNUM}$`))
    await s.page.getByTestId('trigger-row').nth(1).waitFor()
    assert.equal(await s.page.getByTestId('trigger-row').nth(0).getByTestId('trigger-issue').count(), 0)
    assert.match(await s.page.getByTestId('trigger-row').nth(1).getByTestId('trigger-issue').first().innerText(), /trigger-command-unknown/)
    await goto(s.page, '/content/check')
    await s.page.getByTestId('check-run').click()
    await s.page.getByTestId('content-problem').filter({ hasText: "'who: i'" }).click()
    await s.page.waitForURL(new RegExp(`/rooms/${ROOM_VNUM}$`))
    await s.page.getByTestId('trigger-row').first().waitFor()
    const texts = (await s.page.getByTestId('trigger-row').first().getByTestId('trigger-issue').allInnerTexts()).join('\n')
    assert.match(texts, /trigger-condition-invalid/)
    assert.match(texts, /trigger-type-not-allowed/)
  })

  /** La riga (1-based) di `needle` nel file `<name>*.yaml` della zona di prova, come la darebbe il gioco. */
  async function lineOf(name: string, needle: string): Promise<number> {
    const { readFileSync, readdirSync } = await import('node:fs')
    const dir = join(process.env.E2E_DEFINITIONS_PATH!, 'zones', 'ZonaAlfa')
    const file = readdirSync(dir).find((f) => f.startsWith(name))!
    const lines = readFileSync(join(dir, file), 'utf8').split('\n')
    return lines.findIndex((l) => l.includes(needle)) + 1
  }
})
