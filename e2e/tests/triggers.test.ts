/**
 * Trigger dei mob (pachimud): scheda «Trigger» nel mob (aggiunta, azioni una per riga, salvataggio), 422 con code stabile per tipo e
 * probabilità non validi, e problemi `trigger-command-unknown` / `trigger-variable-unknown` del controllo mostrati sulla riga del trigger.
 * Il finto server riporta i problemi scritti in `<socket>.issues.json`.
 */
import assert from 'node:assert/strict'
import { rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import { goto, loginOk, openSession, rawI18nKey, saveForm, type Session } from '../support/browser.ts'

const ISSUES = (): string => join(process.env.E2E_LIVE_SOCKET_DIR!, 'live-pachimud.sock.issues.json')
const MOB_VNUM = 1001
const WORLD = 'pachimud-live'

/** Sceglie un mondo dal selettore nella barra (ricarica la pagina). */
async function pickWorld(s: Session, name: string): Promise<void> {
  await s.page.getByTestId('world-select').click()
  await Promise.all([
    s.page.waitForNavigation({ waitUntil: 'load' }),
    s.page.locator('.q-menu .q-item', { hasText: name }).first().click(),
  ])
}

describe('trigger dei mob', () => {
  let s: Session
  let api: Api

  /** Toglie i trigger dal mob di prova. */
  async function reset(): Promise<void> {
    const mob = await api.byVnum('mobs', MOB_VNUM)
    if (mob) await api.call('PUT', `/api/mobs/${mob.id}`, { extra: { triggers: [] } })
  }

  before(async () => {
    api = (await Api.connect()).inWorld(WORLD)
    await reset()
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    rmSync(ISSUES(), { force: true })
    await s.close()
    await reset()
  })

  it('un trigger si aggiunge dalla scheda, con le azioni una per riga, e si salva', async () => {
    await pickWorld(s, 'Pachimud (live)')
    await goto(s.page, `/mobs/${MOB_VNUM}`)
    await s.page.getByText('Trigger', { exact: true }).first().click()
    await s.page.getByTestId('triggers-hint').waitFor()
    await s.page.getByTestId('trigger-add').click()
    await s.page.getByTestId('trigger-argument').fill('aiuto')
    await s.page.getByTestId('trigger-actions').getByTestId('action-text').first().fill('say Ciao $n')
    await s.page.getByTestId('trigger-actions').getByTestId('action-add').last().click()
    await s.page.getByTestId('trigger-actions').getByTestId('action-text').nth(1).fill('emote sorride a $n')
    await saveForm(s.page)
    const mob = await api.byVnum('mobs', MOB_VNUM)
    const saved = (await api.call('GET', `/api/mobs/${mob.id}`)).data.extra.triggers
    assert.deepEqual(saved, [{ type: 'speech', argument: 'aiuto', chance: 100, actions: ['say Ciao $n', 'emote sorride a $n'] }])
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('nuovi tipi e blocco if/else annidato: si compilano dalla scheda e si salvano', async () => {
    await reset()
    await goto(s.page, `/mobs/${MOB_VNUM}`)
    await s.page.getByText('Trigger', { exact: true }).first().click()
    await s.page.getByTestId('trigger-add').click()
    await s.page.getByTestId('trigger-type').click()
    await s.page.locator('.q-menu .q-item', { hasText: 'fight' }).first().click()
    const actions = s.page.getByTestId('trigger-actions')
    await actions.getByTestId('action-text').first().fill('say Basta!')
    await actions.getByTestId('if-add').last().click()
    const block = actions.getByTestId('if-block').first()
    await block.getByTestId('cond-level').fill('>= 10')
    await block.getByTestId('if-then').first().getByTestId('action-text').first().fill('say Collega!')
    await block.getByTestId('if-else').last().getByTestId('action-add').click()
    await block.getByTestId('if-else').last().getByTestId('action-text').first().fill('say Benvenuto.')
    await saveForm(s.page)
    const mob = await api.byVnum('mobs', MOB_VNUM)
    const saved = (await api.call('GET', `/api/mobs/${mob.id}`)).data.extra.triggers
    assert.equal(saved[0].type, 'fight')
    assert.equal(saved[0].actions[1].if.level, '>= 10')
    assert.deepEqual(saved[0].actions[1].else, ['say Benvenuto.'])
    const bad = await api.call('PUT', `/api/mobs/${mob.id}`, { extra: { triggers: [{ type: 'enter', actions: ['say x'] }] } })
    assert.equal(bad.status, 422)
    assert.equal(JSON.stringify(bad.body).includes('pachimud.invalid_choice'), true)
    const hit = await api.call('PUT', `/api/mobs/${mob.id}`, { extra: { triggers: [{ type: 'hitprcnt', actions: ['flee'] }] } })
    assert.equal(hit.status, 422)
  })

  it('fase 3: nuove condizioni (ora, notte, combattimento, effetto, vnum) e comandi MP del mob', async () => {
    await reset()
    await goto(s.page, `/mobs/${MOB_VNUM}`)
    await s.page.getByText('Trigger', { exact: true }).first().click()
    await s.page.getByTestId('trigger-add').click()
    const actions = s.page.getByTestId('trigger-actions')
    await actions.getByTestId('action-text').first().fill('mpgoto 1002')
    await s.page.getByText('Uso: mpgoto <vnum stanza>').waitFor()
    await actions.getByTestId('if-add').last().click()
    const block = actions.getByTestId('if-block').first()
    await block.getByTestId('cond-time').fill('>= 20')
    await block.getByTestId('cond-vnum').fill('1000')
    await block.getByTestId('cond-is-night').click()
    await block.getByTestId('cond-has-effect').fill('sanctuary')
    await block.getByTestId('if-then').first().getByTestId('action-text').first().fill('mpload obj 1000 inv')
    await block.getByTestId('cond-time').fill('25')
    await s.page.getByText('Un\'ora da 0 a 23').waitFor()
    await block.getByTestId('cond-time').fill('>= 20')
    await saveForm(s.page)
    const mob = await api.byVnum('mobs', MOB_VNUM)
    const saved = (await api.call('GET', `/api/mobs/${mob.id}`)).data.extra.triggers
    assert.deepEqual(
      { ...saved[0].actions[1].if, who: undefined },
      { time: '>= 20', vnum: 1000, is_night: true, has_effect: 'sanctuary', who: undefined },
    )
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('tipo e probabilità non validi sono 422 con code stabile', async () => {
    const mob = await api.byVnum('mobs', MOB_VNUM)
    const put = (t: object) => api.call('PUT', `/api/mobs/${mob.id}`, { extra: { triggers: [t] } })
    const ok = { type: 'death', actions: ['say Ahi'] }
    const bad = await put({ ...ok, type: 'nope' })
    assert.equal(bad.status, 422)
    assert.equal(JSON.stringify(bad.body).includes('pachimud.invalid_choice'), true)
    const range = await put({ ...ok, chance: 101 })
    assert.equal(range.status, 422)
    assert.equal(JSON.stringify(range.body).includes('pachimud.invalid_range'), true)
  })

  it('i problemi del controllo compaiono sulla riga del trigger giusto', async () => {
    const mob = await api.byVnum('mobs', MOB_VNUM)
    await api.call('PUT', `/api/mobs/${mob.id}`, {
      extra: {
        triggers: [
          { type: 'speech', argument: 'aiuto', chance: 100, actions: ['say Ciao $n'] },
          { type: 'greet', argument: '', chance: 100, actions: ['salta', 'say $x'] },
        ],
      },
    })
    writeFileSync(
      ISSUES(),
      JSON.stringify([
        { severity: 'error', code: 'trigger-command-unknown', message: "mob 1001, trigger 1: il comando 'salta' non esiste", file: '/gioco/definitions/zones/ZonaAlfa/mobs.yaml', line: 14 },
        { severity: 'error', code: 'trigger-variable-unknown', message: "mob 1001, trigger 1: la variabile '$x' non esiste", file: '/gioco/definitions/zones/ZonaAlfa/mobs.yaml', line: 14 },
      ])
    )
    await goto(s.page, '/content/check')
    await s.page.getByTestId('check-run').click()
    await s.page.getByTestId('content-problem').first().waitFor()
    await s.page.getByText('Un trigger usa un comando che non esiste', { exact: false }).waitFor()
    await s.page.getByTestId('content-problem').filter({ hasText: "il comando 'salta'" }).click()
    await s.page.waitForURL(new RegExp(`/mobs/${MOB_VNUM}$`))
    await s.page.getByTestId('trigger-row').nth(1).waitFor()
    assert.equal(await s.page.getByTestId('trigger-row').nth(0).getByTestId('trigger-issue').count(), 0)
    const second = s.page.getByTestId('trigger-row').nth(1).getByTestId('trigger-issue')
    assert.equal(await second.count(), 2)
    assert.match(await second.nth(0).innerText(), /trigger-command-unknown[\s\S]*salta/)
    assert.match(await second.nth(1).innerText(), /trigger-variable-unknown[\s\S]*\$x/)
  })
})
