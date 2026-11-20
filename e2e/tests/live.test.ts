/**
 * Canale live verso un MUD acceso (finto server `livectl`, vedi `tests/support/live_fake_cli.py`): API (permessi, capability, sola lettura, errori),
 * pagina Giocatori (stato del canale, badge online, modifica live con avvertenza per gli immortali, pannello «Server live») e ripiego sui file con il
 * canale spento. Mondi: `dikumod-live` (scrivibile), `dikumod-live-ro` (sola lettura). Se i dati di Diku Modificato non esistono la suite si salta.
 */
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { writeFileSync } from 'node:fs'
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
      stdio: ['ignore', 'pipe', 'ignore'], // senza stderr ereditato l'orfano non tiene aperto l'output del runner
      detached: true,
    })
    child.once('error', fail)
    child.stdout!.on('data', (chunk: Buffer) => {
      if (chunk.toString().includes('ready')) {
        process.env.E2E_LIVE_PID = String(child.pid)
        writeFileSync(join(workdir, 'live.pid'), String(child.pid)) // il teardown e' in un altro processo: legge il PID da qui
        child.stdout!.destroy()
        child.unref()
        done()
      }
    })
  })
}

describe('canale live (dikumod)', { skip: HAS_DIKUMOD ? false : 'dati Diku Modificato non trovati (E2E_DIKUMOD)' }, () => {
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
      ['pachimud-live', 'dikumod-live', 'dikumod-live-ro'],
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
    // mob e stanza si scelgono da liste filtrabili di elementi esistenti (nome o vnum), non si digita un vnum a caso
    await d.getByTestId('live-load-vnum').fill('3000')
    await s.page.locator('.q-menu .q-item', { hasText: /#3000\b/ }).first().click()
    await d.getByTestId('live-load-room').fill('3001')
    await s.page.locator('.q-menu .q-item', { hasText: /#3001\b/ }).first().click()
    await d.getByTestId('live-load-go').click()
    await d.getByTestId('live-server-message').filter({ hasText: /1 creati/ }).waitFor()
    await d.getByTestId('live-load-vnum').fill('zzzznessuno')
    await s.page.locator('.q-menu .q-item', { hasText: /Nessun risultato/ }).first().waitFor()
    await s.page.keyboard.press('Escape')
    await d.getByTestId('live-tab-echo').click()
    await d.getByTestId('live-echo-text').fill('Benvenuti dall\'editor')
    await d.getByTestId('live-echo-go').click()
    await d.getByTestId('live-server-message').filter({ hasText: /ricevuto da 1 giocatori/ }).waitFor()
    assert.equal(await rawI18nKey(s.page), null)
    await s.page.keyboard.press('Escape')
    await waitDialogsClosed(s.page)
  })

  /** Inventario live di Tizio via API (elenco piatto). */
  async function inventoryOf(api: Api): Promise<any[]> {
    return (await api.get('/api/world/live/players/Tizio/inventory')).data.items
  }

  /** Percorso API di un oggetto di Tizio (il `ref` contiene `:` e `/`: sta in query). */
  const itemUrl = (ref: string, extra = ''): string => `/api/world/live/players/Tizio/inventory/item?ref=${encodeURIComponent(ref)}${extra}`

  it('API inventario live: elenco, oggetto, expect obbligatorio, stale_ref, avviso vnum, rimozione, sola lettura', async () => {
    const api = (await Api.connect()).inWorld('dikumod-live')
    const worlds = (await (await Api.connect()).get('/api/worlds')).data as { id: string; capabilities: Record<string, boolean> }[]
    assert.deepEqual(worlds.filter((w) => w.capabilities.supportsLiveInventory).map((w) => w.id), ['dikumod-live', 'dikumod-live-ro'])
    assert.ok((await api.get('/api/world/live/status')).data.features.includes('inventory'))
    const items = await inventoryOf(api)
    assert.deepEqual(items.map((i) => [i.ref, i.depth]), [['eq:5', 0], ['inv:0', 0], ['inv:1', 0], ['inv:1/0', 1]])
    const nested = (await api.get(itemUrl('inv:1/0'))).data
    assert.equal(nested.vnum, 3001)
    assert.ok(nested.wearFlags !== undefined && nested.cost !== undefined)
    assert.equal((await api.get(itemUrl('inv:9'))).body.detail[0].code, 'worldlive.not_found')
    // expect obbligatorio (422), impronta vecchia (409 stale_ref) e nulla cambia
    const bottle = items[1]
    const noExpect = await api.call('PATCH', itemUrl('inv:0'), { set: { weight: 3 } })
    assert.equal(noExpect.status, 422)
    const noFp = await api.call('DELETE', itemUrl('inv:0'))
    assert.equal(noFp.status, 422)
    const stale = await api.call('PATCH', itemUrl('inv:0'), { expect: { vnum: bottle.vnum, fp: '00000000' }, set: { weight: 3 } })
    assert.equal(stale.status, 409)
    assert.equal(stale.body.detail[0].code, 'worldlive.stale_ref')
    assert.equal((await inventoryOf(api))[1].weight, bottle.weight)
    // oggetto > 32767: creato con avviso, poi rimosso
    const made = await api.post('/api/world/live/load/obj', { vnum: 35000, player: 'Tizio' })
    assert.deepEqual(made.data.warnings, ['vnum_not_saveable'])
    const high = (await inventoryOf(api)).find((i) => i.vnum === 35000)
    const removed = await api.call('DELETE', itemUrl(high.ref, `&fp=${high.fp}&vnum=${high.vnum}`))
    assert.equal(removed.data.removed, true)
    assert.equal((await inventoryOf(api)).some((i) => i.vnum === 35000), false)
    // sola lettura: letture si', scritture 409 world.read_only
    const ro = api.inWorld('dikumod-live-ro')
    assert.equal((await ro.get('/api/world/live/players/Tizio/inventory')).status, 200)
    const write = await ro.call('PATCH', itemUrl('inv:0'), { expect: { vnum: bottle.vnum, fp: bottle.fp }, set: { weight: 3 } })
    assert.equal(write.body.detail[0].code, 'world.read_only')
    assert.equal((await ro.call('DELETE', itemUrl('inv:0', `&fp=${bottle.fp}&vnum=${bottle.vnum}`))).body.detail[0].code, 'world.read_only')
    // non connesso: errore chiaro
    assert.equal((await api.get('/api/world/live/players/Caio/inventory')).body.detail[0].code, 'worldlive.player_not_playing')
  })

  it('dialogo di un giocatore connesso: inventario LIVE, aggiunta, modifica di ogni gruppo di campi', async () => {
    await s.page.getByTestId('player-open-tizio').click()
    const d = dialog(s.page)
    await d.getByTestId('tab-inventory').click()
    const panel = d.getByTestId('panel-live-inventory')
    assert.match(await panel.getByTestId('live-inventory-badge').innerText(), /LIVE/)
    const table = panel.getByTestId('live-inventory-table')
    for (const ref of ['eq:5', 'inv:0', 'inv:1', 'inv:1/0']) await table.getByTestId(`live-inventory-name-${ref}`).waitFor()
    assert.match(await table.locator('tbody tr').nth(0).innerText(), /giubbotto/i)
    assert.equal(await d.getByTestId('panel-inventory').count(), 0) // non l'inventario su file
    // aggiunta: oggetto esistente scelto da lista filtrabile, creato per il giocatore
    await panel.getByTestId('live-inventory-pick').fill('3001')
    await s.page.locator('.q-menu .q-item', { hasText: /#3001\b/ }).first().click()
    await panel.getByTestId('live-inventory-add').click()
    await s.page.waitForFunction(() => document.querySelectorAll('[data-testid="live-inventory-table"] tbody tr').length === 5)
    const api = (await Api.connect()).inWorld('dikumod-live')
    assert.equal((await inventoryOf(api)).length, 5)
    // gruppo 1: parole chiave, descrizione breve e lunga
    const edit = async (ref: string): Promise<ReturnType<Session['page']['getByTestId']>> => {
      await table.getByTestId(`live-inventory-edit-${ref}`).click()
      const item = s.page.getByTestId('live-item-dialog')
      await item.getByTestId('live-item-meta').waitFor()
      return item
    }
    const apply = async (): Promise<void> => {
      await s.page.getByTestId('live-item-apply').click()
      await s.page.getByTestId('live-item-dialog').waitFor({ state: 'detached' })
    }
    let item = await edit('eq:5')
    await item.getByTestId('live-item-name').fill('giubbotto nero cuoio')
    await item.getByTestId('live-item-short').fill('Un giubbotto nero')
    await item.getByTestId('live-item-description').fill('Un giubbotto nero giace qui.')
    await item.getByTestId('live-item-name').fill('giubbotto $nero') // `$` non ammesso: il pulsante resta spento
    assert.equal(await s.page.getByTestId('live-item-apply').isDisabled(), true)
    await item.getByTestId('live-item-name').fill('giubbotto nero cuoio')
    await apply()
    let vest = (await api.get(itemUrl('eq:5'))).data
    assert.deepEqual([vest.name, vest.shortDescription, vest.description], ['giubbotto nero cuoio', 'Un giubbotto nero', 'Un giubbotto nero giace qui.'])
    await table.getByTestId('live-inventory-name-eq:5').filter({ hasText: 'Un giubbotto nero' }).waitFor()
    // gruppo 2: i 4 valori (etichettati dal tipo), peso e timer
    item = await edit('eq:5')
    await item.getByTestId('live-item-value-0').fill('7')
    await item.getByTestId('live-item-value-3').fill('4')
    await item.getByTestId('live-item-weight').fill('9')
    await item.getByTestId('live-item-timer').fill('600')
    assert.match(await item.innerText(), /Bonus CA/) // giubbotto = armatura: valore 0 etichettato
    await apply()
    vest = (await api.get(itemUrl('eq:5'))).data
    assert.deepEqual([vest.values, vest.weight, vest.timer], [[7, 2, 0, 4], 9, 600])
    // gruppo 3: extra flag (selezione multipla dall'enum) e affect (dove + modifica)
    item = await edit('eq:5')
    await item.getByTestId('live-item-flags').click()
    await s.page.locator('.q-menu .q-item', { hasText: /^\s*glow\s*$/ }).first().click()
    await s.page.keyboard.press('Escape')
    await item.getByTestId('live-item-affect-0-location').click()
    await s.page.locator('.q-menu .q-item', { hasText: /^\s*hit\s*$/ }).first().click()
    await item.getByTestId('live-item-affect-0-modifier').fill('5')
    await apply()
    vest = (await api.get(itemUrl('eq:5'))).data
    assert.equal(vest.extraFlags & 1, 1)
    assert.deepEqual(vest.affects[0], { location: 13, modifier: 5 })
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('modifica concorrente: stale_ref con messaggio chiaro, elenco ricaricato, input conservato', async () => {
    const table = s.page.getByTestId('panel-live-inventory').getByTestId('live-inventory-table') // niente `dialog()`: l'ultimo dialogo sara' quello di modifica
    await table.getByTestId('live-inventory-edit-eq:5').click()
    const item = s.page.getByTestId('live-item-dialog')
    await item.getByTestId('live-item-meta').waitFor()
    // qualcun altro cambia la descrizione breve dopo che il dialogo ha letto l'oggetto
    const api = (await Api.connect()).inWorld('dikumod-live')
    const current = (await api.get(itemUrl('eq:5'))).data
    const other = await api.call('PATCH', itemUrl('eq:5'), { expect: { vnum: current.vnum, fp: current.fp }, set: { shortDescription: 'Un giubbotto altrui' } })
    assert.equal(other.status, 200)
    await item.getByTestId('live-item-weight').fill('11')
    await s.page.getByTestId('live-item-apply').click()
    await item.getByTestId('live-item-stale').waitFor()
    assert.match(await item.getByTestId('live-item-stale').innerText(), /cambiato nel frattempo/)
    assert.equal(await item.getByTestId('live-item-weight').inputValue(), '11') // l'input non si perde
    assert.equal((await api.get(itemUrl('eq:5'))).data.weight, 9) // e il gioco non e' stato toccato
    await table.getByTestId('live-inventory-name-eq:5').filter({ hasText: 'Un giubbotto altrui' }).waitFor() // elenco ricaricato
    assert.equal(await s.page.getByTestId('live-item-apply').isDisabled(), true) // mai un nuovo invio automatico
    await item.getByTestId('live-item-rebase').click()
    await item.getByTestId('live-item-stale').waitFor({ state: 'detached' })
    assert.equal(await item.getByTestId('live-item-weight').inputValue(), '11')
    await s.page.getByTestId('live-item-apply').click()
    await item.waitFor({ state: 'detached' })
    const after = (await api.get(itemUrl('eq:5'))).data
    assert.deepEqual([after.weight, after.shortDescription], [11, 'Un giubbotto altrui'])
  })

  it('rimozione con conferma: un contenitore porta con se\' il contenuto; annulla non toglie nulla', async () => {
    const table = s.page.getByTestId('panel-live-inventory').getByTestId('live-inventory-table')
    const api = (await Api.connect()).inWorld('dikumod-live')
    const before = (await inventoryOf(api)).length
    const bag = table.locator('tbody tr', { hasText: 'piccola borsa' })
    await bag.locator('[data-testid^="live-inventory-remove-"]').click()
    const confirmBox = s.page.locator('.q-dialog').last()
    assert.match(await confirmBox.innerText(), /distrutto.*1 oggetti|1 oggetti.*non si annulla/s)
    await confirmBox.getByRole('button', { name: 'Annulla' }).click()
    assert.equal((await inventoryOf(api)).length, before)
    await bag.locator('[data-testid^="live-inventory-remove-"]').click()
    await s.page.getByTestId('live-inventory-remove-confirm').click()
    await s.page.waitForFunction((n) => document.querySelectorAll('[data-testid="live-inventory-table"] tbody tr').length === n, before - 2)
    assert.equal((await inventoryOf(api)).some((i) => i.vnum === 14), false)
    assert.equal(await rawI18nKey(s.page), null)
    await closeAll(s)
  })

  it('«Server live», crea: oggetto per un giocatore con «Modifica»; in una stanza la nota; avviso vnum non salvabile', async () => {
    await s.page.getByTestId('live-open').click()
    const d = s.page.getByTestId('live-server-dialog')
    await d.getByTestId('live-tab-load').click()
    await d.getByTestId('live-load-kind-obj').click()
    await d.getByTestId('live-load-where-room').click()
    assert.match(await d.getByTestId('live-load-room-note').innerText(), /inventario di un giocatore/) // limite: gli oggetti a terra non si modificano
    await d.getByTestId('live-load-where-player').click()
    await d.getByTestId('live-load-vnum').fill('3001')
    await s.page.locator('.q-menu .q-item', { hasText: /#3001\b/ }).first().click()
    await d.getByTestId('live-load-player').click()
    await s.page.locator('.q-menu .q-item', { hasText: 'Tizio' }).first().click()
    await d.getByTestId('live-load-go').click()
    await d.getByTestId('live-server-message').filter({ hasText: /1 creati/ }).waitFor()
    await d.getByTestId('live-load-edit').click()
    const item = s.page.getByTestId('live-item-dialog')
    await item.getByTestId('live-item-meta').waitFor()
    await item.getByTestId('live-item-short').fill('Una bottiglia speciale')
    await s.page.getByTestId('live-item-apply').click()
    await item.waitFor({ state: 'detached' })
    const api = (await Api.connect()).inWorld('dikumod-live')
    const items = await inventoryOf(api)
    assert.equal(items.find((i) => i.slot === null).shortDescription, 'Una bottiglia speciale') // il nuovo e' in testa all'inventario portato
    assert.equal(items.filter((i) => i.shortDescription === 'Una bottiglia speciale').length, 1)
    // avviso del MUD (oggetto oltre 32767): la risposta e' simulata perche' il finto MUD conosce solo alcuni vnum
    await s.page.route('**/api/world/live/load/obj', (route) =>
      route.fulfill({ json: { success: true, message: 'ok', data: { loaded: [{ vnum: 40019, name: 'x', where: 'player' }], warnings: ['vnum_not_saveable'] } } }),
    )
    await d.getByTestId('live-load-vnum').fill('40019')
    await s.page.locator('.q-menu .q-item', { hasText: /#40019\b/ }).first().click()
    await d.getByTestId('live-load-go').click()
    assert.match(await d.getByTestId('live-server-warning').innerText(), /32767/)
    await s.page.unroute('**/api/world/live/load/obj')
    assert.equal(await rawI18nKey(s.page), null)
    await s.page.keyboard.press('Escape')
    await waitDialogsClosed(s.page)
  })

  it('inventario su file: un oggetto oltre 32767 non e\' selezionabile e l\'errore spiega il limite', async () => {
    await s.page.getByTestId('player-open-mevio').click()
    const d = dialog(s.page)
    await d.getByTestId('tab-inventory').click()
    await d.getByTestId('panel-inventory').waitFor()
    assert.equal(await d.getByTestId('panel-live-inventory').count(), 0) // non connesso: il file
    await d.getByTestId('confirm-server').click() // server acceso (provato dal canale): senza conferma le scritture su file sono spente
    await d.getByTestId('inventory-add').click()
    await d.getByTestId('inventory-pick').fill('40019')
    const option = s.page.locator('.q-menu .q-item', { hasText: /#40019\b/ }).first()
    await option.waitFor()
    assert.match(await option.innerText(), /non salvabile nel rent/)
    assert.equal(await option.getAttribute('aria-disabled'), 'true')
    await s.page.keyboard.press('Escape')
    const rw = (await Api.connect()).inWorld('dikumod-rw')
    const refused = await rw.post('/api/world/players/caio/inventory/items', { vnum: 40019 })
    assert.equal(refused.status, 422)
    assert.equal(refused.body.detail[0].code, 'worldplayers.invalid_value')
    assert.match(refused.body.detail[0].msg, /32767/)
    assert.equal(await rawI18nKey(s.page), null)
    await s.page.keyboard.press('Escape')
    await closeAll(s)
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
    await d.getByTestId('tab-inventory').click()
    await d.getByTestId('live-inventory-name-eq:5').waitFor() // l'inventario live si legge
    assert.equal(await d.locator('[data-testid^="live-inventory-edit-"], [data-testid^="live-inventory-remove-"], [data-testid="live-inventory-add"]').count(), 0)
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
    await d.getByTestId('tab-inventory').click()
    await d.getByTestId('panel-inventory').waitFor() // ripiego sul file
    assert.equal(await d.getByTestId('panel-live-inventory').count(), 0)
    await s.page.keyboard.press('Escape')
    await waitDialogsClosed(s.page)
    await startFake()
    await s.page.getByRole('button', { name: 'Ricarica' }).first().click()
    await goto(s.page, '/player-files')
    await s.page.getByTestId('live-status').filter({ hasText: /attivo/ }).waitFor()
  })
})
