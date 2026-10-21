/**
 * Canale live verso un MUD acceso (finto server `livectl`, vedi `tests/support/live_fake_cli.py`): API (permessi, capability, sola lettura, errori),
 * pagina Giocatori (stato del canale, badge online, modifica live con avvertenza per gli immortali, pannello «Server live») e ripiego sui file con il
 * canale spento. Mondi: `dikumod-live` (scrivibile), `dikumod-live-ro` (sola lettura). Se `E2E_DIKUMOD` non e' impostata la suite si salta.
 */
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { join } from 'node:path'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import { BACKEND, HAS_DIKUMOD, LIVE_SOCKET, LIVE_TOKEN } from '../support/stack.ts'
import { dialog, goto, loginOk, openSession, rawI18nKey, tableRow, waitDialogsClosed, type Session } from '../support/browser.ts'

/** Sceglie un mondo dal selettore nella barra (ricarica la pagina). */
async function pickWorld(s: Session, name: string): Promise<void> {
  await s.page.getByTestId('world-select').click()
  await Promise.all([
    s.page.waitForNavigation({ waitUntil: 'load' }),
    s.page.locator('.q-menu .q-item', { hasText: name }).first().click(),
  ])
}

/** Chiude tutti i dialog impilati (un Escape alla volta: ognuno chiude solo quello in cima). */
async function closeAll(s: Session): Promise<void> {
  for (let i = 0; i < 6 && (await s.page.locator('.q-dialog').count()) > 0; i++) {
    await s.page.locator('.q-dialog').last().focus().catch(() => undefined)
    await s.page.keyboard.press('Escape')
    await s.page.waitForTimeout(500)
  }
  await waitDialogsClosed(s.page)
}

/** Ferma il finto server (come un MUD spento: il file del socket resta, la connessione e' rifiutata). */
function stopFake(): void {
  process.kill(Number(process.env.E2E_LIVE_PID), 'SIGKILL')
}

/** Riavvia il finto server sullo stesso socket (stato iniziale) e ricorda il nuovo PID per il teardown. */
async function startFake(): Promise<void> {
  const workdir = process.env.E2E_LIVE_SOCKET_DIR!
  await new Promise<void>((done, fail) => {
    const child = spawn(join(BACKEND, '.venv', 'bin', 'python'), ['-m', 'tests.support.live_fake_cli', LIVE_SOCKET(workdir), LIVE_TOKEN], {
      cwd: BACKEND,
      stdio: ['ignore', 'pipe', 'inherit'],
      detached: true,
    })
    child.once('error', fail)
    child.stdout!.on('data', (chunk: Buffer) => {
      if (chunk.toString().includes('ready')) {
        process.env.E2E_LIVE_PID = String(child.pid)
        child.stdout!.destroy()
        child.unref()
        done()
      }
    })
  })
}

describe('canale live (dikumod)', { skip: HAS_DIKUMOD ? false : 'E2E_DIKUMOD non impostata' }, () => {
  let s: Session

  before(async () => {
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await s.close()
  })

  it('API: capability solo nei mondi con canale, stato, letture e permessi', async () => {
    const api = await Api.connect()
    const worlds = (await api.get('/api/worlds')).data as { id: string; capabilities: Record<string, boolean> }[]
    assert.deepEqual(
      worlds.filter((w) => w.capabilities.supportsLive).map((w) => w.id),
      ['dikumod-live', 'dikumod-live-ro'],
    )
    const live = api.inWorld('dikumod-live')
    const status = (await live.get('/api/world/live/status')).data
    assert.equal(status.state, 'connected')
    assert.ok(status.classes.includes('write') && status.commands.includes('player.set'))
    assert.doesNotMatch(JSON.stringify(status), new RegExp(`${LIVE_TOKEN}|live\\.sock`)) // né token né percorso del socket
    assert.deepEqual(
      ((await live.get('/api/world/live/who')).data.players as { name: string }[]).map((p) => p.name).sort(),
      ['Caio', 'Tizio'],
    )
    assert.equal((await api.inWorld('dikumod').get('/api/world/live/status')).status, 409) // senza capability
    assert.equal((await fetch(`${new URL('/api/world/live/status', process.env.E2E_BASE_URL ?? 'http://127.0.0.1:8124')}`, { headers: { 'x-world': 'dikumod-live' } })).status, 401)
    const ro = api.inWorld('dikumod-live-ro')
    assert.equal((await ro.get('/api/world/live/who')).status, 200)
    const write = await ro.post('/api/world/live/echo', { text: 'x', all: true })
    assert.equal(write.status, 409)
    assert.equal(write.body.detail[0].code, 'world.read_only')
  })

  it('API: errori del MUD con codici stabili e immortali solo con conferma', async () => {
    const live = (await Api.connect()).inWorld('dikumod-live')
    const missing = await live.get('/api/world/live/players/Nessuno')
    assert.equal(missing.status, 404)
    assert.equal(missing.body.detail[0].code, 'worldlive.not_found')
    const range = await live.call('PATCH', '/api/world/live/players/Tizio', { fields: { gold: -1 } })
    assert.equal(range.status, 422)
    assert.equal(range.body.detail[0].code, 'worldlive.value_out_of_range')
    const denied = await live.call('PATCH', '/api/world/live/players/Tizio', { fields: { levels: { warrior: 52 } } })
    assert.equal(denied.status, 409)
    assert.equal(denied.body.detail[0].code, 'worldlive.immortal_confirmation_required')
    assert.deepEqual((await live.get('/api/world/live/players/Tizio')).data.fields.levels, { warrior: 12 })
  })

  it('pagina: stato del canale, badge online e link morto; i non connessi restano senza badge', async () => {
    await goto(s.page, '/')
    await pickWorld(s, 'Diku Modificato (live)')
    await goto(s.page, '/player-files')
    await s.page.getByTestId('live-status').filter({ hasText: /attivo/ }).waitFor()
    await tableRow(s.page, 'Tizio').waitFor()
    assert.match(await s.page.getByTestId('player-online-tizio').innerText(), /online/)
    assert.match(await s.page.getByTestId('player-online-caio').innerText(), /link morto/)
    assert.equal(await s.page.getByTestId('player-online-mevio').count(), 0)
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('giocatore connesso: la modifica passa dal canale; livello >= 51 solo dopo l\'avvertenza esplicita', async () => {
    await s.page.getByTestId('player-open-tizio').click()
    const d = dialog(s.page)
    await d.getByTestId('player-online-note').waitFor()
    assert.match(await d.getByTestId('player-online-note').innerText(), /canale live/)
    assert.equal(await d.getByTestId('edit-start').count(), 0) // niente modifica su file per un connesso
    await d.getByTestId('live-edit-start').click()
    const live = s.page.getByTestId('live-player-dialog')
    await live.getByTestId('live-field-gold').fill('777')
    await s.page.getByTestId('live-apply').click()
    await live.getByTestId('live-player-result').waitFor()
    assert.match(await live.getByTestId('live-player-result').innerText(), /salvati dal gioco/)
    const api = (await Api.connect()).inWorld('dikumod-live')
    assert.equal((await api.get('/api/world/live/players/Tizio')).data.fields.gold, 777)
    // immortale: avvertenza, annulla = nulla cambia
    await live.getByTestId('live-level-warrior').fill('55')
    await s.page.getByTestId('live-apply').click()
    const warning = s.page.locator('.q-dialog').last()
    await warning.getByText(/stai creando un immortale/i).waitFor()
    await warning.getByTestId('immortal-cancel').click()
    assert.deepEqual((await api.get('/api/world/live/players/Tizio')).data.fields.levels, { warrior: 12 })
    // conferma: solo ora parte confirmImmortal
    await s.page.getByTestId('live-apply').click()
    await s.page.locator('.q-dialog').last().getByTestId('immortal-confirm').click()
    for (let i = 0; i < 30; i++) {
      if ((await api.get('/api/world/live/players/Tizio')).data.fields.levels.warrior === 55) break
      await new Promise((r) => setTimeout(r, 200))
    }
    assert.deepEqual((await api.get('/api/world/live/players/Tizio')).data.fields.levels, { warrior: 55 })
    assert.equal(await rawI18nKey(s.page), null)
    await closeAll(s)
  })

  it('pannello «Server live»: giocatori, info, reset zona con conferma, crea mob, messaggio', async () => {
    await s.page.getByTestId('live-open').click()
    const d = s.page.getByTestId('live-server-dialog')
    await d.getByTestId('live-who-Tizio').waitFor()
    await d.getByTestId('live-who-Caio').waitFor()
    await d.getByTestId('live-tab-info').click()
    await d.getByTestId('live-info-table').waitFor()
    assert.match(await d.getByTestId('live-info-mud').innerText(), /FakeMUD/)
    await d.getByTestId('live-tab-zone').click()
    await d.getByTestId('live-zone-select').click()
    await s.page.locator('.q-menu .q-item', { hasText: 'Midgaard' }).first().click()
    await d.getByTestId('live-zone-reset').click()
    await s.page.locator('.q-dialog').last().getByTestId('live-zone-confirm').click()
    await d.getByTestId('live-server-message').filter({ hasText: /Midgaard resettata/ }).waitFor()
    await d.getByTestId('live-tab-load').click()
    await d.getByTestId('live-load-vnum').fill('3000')
    await d.getByTestId('live-load-room').fill('3001')
    await d.getByTestId('live-load-go').click()
    await d.getByTestId('live-server-message').filter({ hasText: /1 creati/ }).waitFor()
    await d.getByTestId('live-load-vnum').fill('1')
    await d.getByTestId('live-load-go').click() // vnum inesistente: errore del MUD tradotto, nessun dialog di errore rumoroso
    await d.getByTestId('live-server-error').waitFor()
    await d.getByTestId('live-tab-echo').click()
    await d.getByTestId('live-echo-text').fill('Benvenuti dall\'editor')
    await d.getByTestId('live-echo-go').click()
    await d.getByTestId('live-server-message').filter({ hasText: /ricevuto da 1 giocatori/ }).waitFor()
    assert.equal(await rawI18nKey(s.page), null)
    await s.page.keyboard.press('Escape')
    await waitDialogsClosed(s.page)
  })

  it('giocatore NON connesso: resta la modifica su file e, col server acceso, serve la conferma', async () => {
    await s.page.getByTestId('player-open-mevio').click()
    const d = dialog(s.page)
    await d.getByTestId('edit-start').waitFor()
    assert.equal(await d.getByTestId('live-edit-start').count(), 0)
    await d.getByTestId('player-server-running').waitFor() // il canale prova che il server e' acceso
    await s.page.keyboard.press('Escape')
    await waitDialogsClosed(s.page)
  })

  it('mondo in sola lettura: nessun controllo di scrittura, letture si\'', async () => {
    await goto(s.page, '/')
    await pickWorld(s, 'Diku Modificato (live, sola lettura)')
    await goto(s.page, '/player-files')
    await s.page.getByTestId('live-status').filter({ hasText: /attivo/ }).waitFor()
    await s.page.getByTestId('player-open-tizio').click()
    const d = dialog(s.page)
    await d.getByTestId('player-readonly-note').waitFor()
    assert.equal(await d.getByTestId('live-edit-start').count(), 0)
    assert.equal(await d.getByTestId('edit-start').count(), 0)
    await s.page.keyboard.press('Escape')
    await waitDialogsClosed(s.page)
    await s.page.getByTestId('live-open').click()
    const panel = s.page.getByTestId('live-server-dialog')
    await panel.getByTestId('live-who-Tizio').waitFor()
    for (const tab of ['zone', 'load', 'echo']) assert.equal(await panel.getByTestId(`live-tab-${tab}`).count(), 0)
    await s.page.keyboard.press('Escape')
    await waitDialogsClosed(s.page)
  })

  it('canale spento: stato chiaro, nessun errore rumoroso, ripiego sui file; poi torna', async () => {
    stopFake()
    await goto(s.page, '/')
    await pickWorld(s, 'Diku Modificato (live)')
    await goto(s.page, '/player-files')
    await s.page.getByTestId('live-status').filter({ hasText: /non raggiungibile/ }).waitFor()
    await tableRow(s.page, 'Tizio').waitFor()
    assert.equal(await s.page.getByTestId('players-error').count(), 0)
    assert.equal(await s.page.getByTestId('live-open').count(), 0)
    assert.equal(await s.page.locator('[data-testid^=player-online-]').count(), 0)
    const api = (await Api.connect()).inWorld('dikumod-live')
    assert.equal((await api.get('/api/world/live/status')).data.state, 'unreachable')
    assert.equal((await api.get('/api/world/live/who')).body.detail[0].code, 'worldlive.unreachable')
    await s.page.getByTestId('player-open-tizio').click()
    const d = dialog(s.page)
    await d.getByTestId('edit-start').waitFor() // file: nessuna modifica live
    assert.equal(await d.getByTestId('live-edit-start').count(), 0)
    await s.page.keyboard.press('Escape')
    await waitDialogsClosed(s.page)
    await startFake()
    await s.page.getByRole('button', { name: 'Ricarica' }).first().click()
    await goto(s.page, '/player-files')
    await s.page.getByTestId('live-status').filter({ hasText: /attivo/ }).waitFor()
  })
})
