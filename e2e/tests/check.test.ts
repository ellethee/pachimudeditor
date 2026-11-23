/**
 * Controllo dei contenuti (pachimud): pagina «Controllo» con i problemi di `content.validate` raggruppati per codice, cliccabili fino
 * alla voce (stanza, mob), e consigli di stile (con contatori) nelle schede di mob e stanza. Il finto server riporta i problemi scritti
 * in `<socket>.issues.json`.
 */
import assert from 'node:assert/strict'
import { rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import { goto, loginOk, openSession, type Session } from '../support/browser.ts'

const ISSUES = (): string => join(process.env.E2E_LIVE_SOCKET_DIR!, 'live-pachimud.sock.issues.json')
const MOB_VNUM = 1001

/** Sceglie un mondo dal selettore nella barra (ricarica la pagina). */
async function pickWorld(s: Session, name: string): Promise<void> {
  await s.page.getByTestId('world-select').click()
  await Promise.all([
    s.page.waitForNavigation({ waitUntil: 'load' }),
    s.page.locator('.q-menu .q-item', { hasText: name }).first().click(),
  ])
}

describe('controllo dei contenuti', () => {
  let s: Session
  let api: Api
  let shortBefore = ''

  before(async () => {
    api = await Api.connect()
    s = await openSession()
    await loginOk(s.page)
    // percorsi del gioco diversi da quelli dell'editor: l'editor li ritrova dal ramo `zones/<zona>/<file>`
    writeFileSync(
      ISSUES(),
      JSON.stringify([
        { severity: 'warning', code: 'exit-one-way', message: 'stanza 1000: uscita north senza ritorno', file: '/gioco/definitions/zones/ZonaAlfa/rooms.yaml', line: 8 },
        { severity: 'warning', code: 'mob-never-loaded', message: 'mob 1001 mai caricato', file: '/gioco/definitions/zones/ZonaAlfa/mobs.yaml', line: 13 },
        { severity: 'warning', code: 'style-short', message: 'mob 1001: corta troppo lunga', file: '/gioco/definitions/zones/ZonaAlfa/mobs.yaml', line: 14 },
        { severity: 'error', code: 'yaml-syntax', message: 'file altrove', file: '/altrove/noto.yaml', line: 1 },
      ])
    )
  })
  after(async () => {
    rmSync(ISSUES(), { force: true })
    if (shortBefore) {
      const mob = await api.byVnum('mobs', MOB_VNUM)
      if (mob) await api.call('PUT', `/api/mobs/${mob.id}`, { shortDescription: shortBefore })
    }
    await s.close()
  })

  it('i problemi sono raggruppati per codice, spiegati e aprono la voce', async () => {
    await pickWorld(s, 'Pachimud (live)')
    await goto(s.page, '/content/check')
    await s.page.getByTestId('check-empty').waitFor()
    await s.page.getByTestId('check-run').click()
    await s.page.getByTestId('content-problem-group').first().waitFor()
    assert.equal(await s.page.getByTestId('content-problem-group').count(), 4)
    await s.page.getByText("Un'uscita verso una stanza della stessa zona che non ha nessuna uscita di ritorno.").waitFor()
    // il file ignoto all'editor non è cliccabile, gli altri sì
    await s.page.getByTestId('content-problem-open').first().waitFor()
    assert.equal(await s.page.getByTestId('content-problem-open').count(), 3)
    await s.page.getByTestId('content-problem').filter({ hasText: 'uscita north senza ritorno' }).click()
    await s.page.waitForURL(/\/rooms\/1000$/)
    await goto(s.page, '/content/check')
    await s.page.getByTestId('check-strict').click()
    await s.page.getByTestId('check-run').click()
    await s.page.getByTestId('content-problem').filter({ hasText: 'mob 1001 mai caricato' }).click()
    await s.page.waitForURL(/\/mobs\/1001$/)
  })

  it('la scheda del mob mostra il contatore e i consigli di stile (non bloccanti)', async () => {
    const mob = await api.byVnum('mobs', MOB_VNUM)
    shortBefore = (await api.call('GET', `/api/mobs/${mob.id}`)).data.shortDescription
    await api.call('PUT', `/api/mobs/${mob.id}`, { shortDescription: 'Un ratto grosso grosso grosso grosso grosso grosso.' })
    await goto(s.page, `/mobs/${MOB_VNUM}`)
    await s.page.getByTestId('style-hints').waitFor()
    const text = await s.page.getByTestId('style-hints').innerText()
    assert.match(text, /descrizione corta ha 51 caratteri, il massimo consigliato è 40/)
    assert.ok((await s.page.locator('.q-field__counter').count()) >= 1)
    await api.call('PUT', `/api/mobs/${mob.id}`, { shortDescription: shortBefore })
    await goto(s.page, `/mobs/${MOB_VNUM}`)
    await s.page.getByTestId('form-save').waitFor()
    assert.equal(await s.page.getByTestId('style-hints').count(), 0)
  })
})
