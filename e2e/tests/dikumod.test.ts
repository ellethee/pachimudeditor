/**
 * Mondo Diku Modificato (Diku molto modificato, su file): descrittori dal backend, selettore, zone, stanze, mob corrotti, sola lettura,
 * scritture sulla copia scrivibile (`dikumod-rw`, con diff completo dei dati) e script di reset con `ifValue`.
 * I dati sono copie temporanee della cartella `lib/` indicata da `E2E_DIKUMOD` (default: la `lib/` di `leu`) (vedi `support/stack.ts`); se la cartella
 * non esiste l'intera suite viene saltata. Gli originali non si toccano.
 */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import { HAS_DIKUMOD } from '../support/stack.ts'
import { dialog, goto, loginOk, openSession, rawI18nKey, saveDialog, saveForm, tableRow, type Session, waitDialogsClosed } from '../support/browser.ts'

/** Sceglie un mondo dal selettore nella barra (ricarica la pagina). */
async function pickWorld(s: Session, name: string): Promise<void> {
  await s.page.getByTestId('world-select').click()
  await Promise.all([
    s.page.waitForNavigation({ waitUntil: 'load' }),
    s.page.locator('.q-menu .q-item', { hasText: name }).first().click(),
  ])
}

/** Scarica tutte le entita' di un tipo (mob, stanze, oggetti) del mondo, indicizzate per id. */
async function snapshot(api: Api, path: string): Promise<Map<number, unknown>> {
  const items = (await api.get(`${path}?pageSize=5000`)).data.items as { id: number }[]
  return new Map(items.map((item) => [item.id, item]))
}

/** Ids delle entita' diverse tra due snapshot (aggiunte, tolte o cambiate). */
function changedIds(before: Map<number, unknown>, after: Map<number, unknown>): number[] {
  const ids = new Set([...before.keys(), ...after.keys()])
  return [...ids].filter((id) => JSON.stringify(before.get(id)) !== JSON.stringify(after.get(id)))
}

describe('dikumod', { skip: HAS_DIKUMOD ? false : 'dati Diku Modificato non trovati (E2E_DIKUMOD)' }, () => {
  let s: Session
  let ro: Api
  let rw: Api
  /** Un mob corrotto e la sua zona. */
  let corrupted: { id: number; zoneId: number }

  before(async () => {
    const api = await Api.connect()
    ro = api.inWorld('dikumod')
    rw = api.inWorld('dikumod-rw')
    const mobs = (await ro.get('/api/mobs?pageSize=5000')).data.items as { id: number; zoneId: number; extra: Record<string, unknown> }[]
    corrupted = mobs.find((m) => m.extra.corrupted === true)!
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await s.close()
  })

  it('/api/worlds: i descrittori di Diku Modificato arrivano dal backend', async () => {
    const worlds = (await (await Api.connect()).get('/api/worlds')).data as {
      id: string
      capabilities: Record<string, boolean>
      resources: { type: string; createAtEnd: boolean; fields: { name: string; readOnly: boolean; unsupported: boolean }[]; extraFields: { name: string; type: string; enum: string | null; group: string | null }[] }[]
    }[]
    const dikumod = worlds.find((w) => w.id === 'dikumod')!
    assert.equal(dikumod.capabilities.readOnly, true)
    assert.equal(worlds.find((w) => w.id === 'dikumod-rw')!.capabilities.readOnly, false)
    // capability: solo script di reset ed extra description
    assert.equal(dikumod.capabilities.supportsResetScripts, true)
    assert.equal(dikumod.capabilities.supportsExtraDescriptions, true)
    for (const cap of ['supportsWorldOverview', 'supportsInstances', 'supportsPlayers', 'supportsTransfer', 'supportsContentRaces']) {
      assert.equal(dikumod.capabilities[cap], false, cap)
    }
    const res = (type: string) => dikumod.resources.find((r) => r.type === type)!
    const names = (type: string) => res(type).extraFields.map((f) => f.name)
    for (const key of ['shop', 'script', 'immune', 'mImmune', 'susc', 'kind', 'multiAttack', 'corrupted']) assert.ok(names('mob').includes(key), key)
    for (const key of ['tele', 'river', 'light', 'sector']) assert.ok(names('room').includes(key), key)
    assert.ok(names('object').includes('affects') && names('exit').includes('exitInfo'))
    assert.equal(res('mob').extraFields.find((f) => f.name === 'immune')!.enum, 'dikumodImmuneFlags')
    assert.equal(res('mob').extraFields.find((f) => f.name === 'corrupted')!.group, 'diagnostic')
    assert.equal(res('zone').createAtEnd, true)
    assert.equal(res('zone').fields.find((f) => f.name === 'bottomVnum')!.readOnly, true)
    assert.equal(res('mob').fields.find((f) => f.name === 'classId')!.unsupported, true)
    assert.equal(res('reset_command').fields.find((f) => f.name === 'ifValue')!.unsupported, false)
    // pachimud dichiara le sue chiavi (file YAML: area, statistiche dei mob, campi del tipo degli oggetti) ma non le regole di Diku Modificato
    const pachimud = worlds.find((w) => w.id === 'pachimud')!
    assert.equal(pachimud.resources.every((r) => !r.createAtEnd), true)
    const pNames = (type: string) => pachimud.resources.find((r) => r.type === type)!.extraFields.map((f) => f.name)
    assert.deepEqual(pNames('room'), ['enabled', 'area'])
    assert.ok(pNames('object').includes('typeFields') && pNames('mob').includes('shop') && pachimud.capabilities.supportsInstances === false)
  })

  it('cambia mondo dal selettore: il menu mostra solo le funzioni supportate', async () => {
    await goto(s.page, '/')
    await s.page.getByTestId('world-select').waitFor()
    await pickWorld(s, 'Diku Modificato (sola lettura)')
    await s.page.getByTestId('world-readonly').waitFor()
    await s.page.locator('.pachi-hub-dash__grid').getByText('Zone', { exact: true }).first().waitFor()
    for (const title of ['Panoramica', 'Istanze', 'Trasferimento zone', 'Razze', 'Classi']) {
      assert.equal(await s.page.locator('.pachi-hub-dash__grid').getByText(title, { exact: true }).count(), 0, title)
    }
    // i giocatori su file (sola lettura) sono l'unica voce «Giocatori» di questo mondo: la pagina di pachimud (/players) non c'e'
    assert.equal(await s.page.locator('.pachi-hub-dash__grid').getByText('Giocatori', { exact: true }).count(), 1)
    await goto(s.page, '/instances')
    await s.page.locator('.pachi-hub-dash__grid').waitFor()
    assert.equal(new URL(s.page.url()).pathname, '/')
  })

  it('zone: elenco plausibile, range derivato e zona senza vnum', async () => {
    const zones = (await ro.get('/api/zones?pageSize=500')).data
    assert.ok(zones.total >= 90 && zones.total <= 100, `zone: ${zones.total}`)
    await goto(s.page, '/zones')
    await tableRow(s.page, 'LIMBO').waitFor()
    assert.match(await tableRow(s.page, 'LIMBO').innerText(), /1-49/)
    assert.match(await tableRow(s.page, 'Scratch Zone').innerText(), /senza vnum/)
    assert.equal(await s.page.getByRole('button', { name: 'Nuova zona' }).count(), 0)
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('zona: bottomVnum derivato, campi senza equivalente disabilitati, chiavi extra dal backend', async () => {
    await goto(s.page, '/zones?zoneId=2')
    await s.page.getByLabel('Nome *').waitFor()
    assert.equal(await s.page.getByLabel('Nome *').inputValue(), 'Temple Extensions')
    assert.equal(await s.page.getByLabel('Vnum minimo').isDisabled(), true)
    assert.equal(await s.page.getByLabel('Builder').isDisabled(), true)
    assert.equal(await s.page.getByLabel('Livello minimo').isDisabled(), true)
    await s.page.getByText('Campi specifici del mondo').click()
    await s.page.getByLabel('Numero di zona (#N)').waitFor()
    assert.equal(await s.page.getByLabel('Indice nel file').isDisabled(), true)
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('stanza: apre la vista con gli extra di Diku Modificato (teleport) e l\'uscita', async () => {
    await goto(s.page, '/rooms?zoneId=1&roomId=5')
    await s.page.getByLabel('Nome *').waitFor()
    assert.equal(await s.page.getByLabel('Nome *').inputValue(), 'La carrozza di ALMA')
    // il settore proprio del mondo ha la precedenza sull'approssimazione
    await s.page.getByText('Campi specifici del mondo').click()
    await s.page.getByLabel('Teleport (time, target, mask, count)').waitFor()
    assert.match(await s.page.getByLabel('Teleport (time, target, mask, count)').inputValue(), /"target": 6/)
    await s.page.getByLabel('Settore del mondo').waitFor()
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('mob corrotto: banner, form in sola lettura, nessun salvataggio ne\' eliminazione', async () => {
    await goto(s.page, `/mobs?zoneId=${corrupted.zoneId}&mobId=${corrupted.id}`)
    await s.page.locator('[data-test="record-corrupted"]').waitFor()
    assert.match(await s.page.locator('[data-test="record-corrupted"]').innerText(), /Record corrotto/)
    assert.equal(await s.page.getByLabel('Descrizione breve *').isDisabled(), true)
    assert.equal(await s.page.getByTestId('form-save').count(), 0)
    // niente pulsante di eliminazione sulla riga (in un mondo di sola lettura non c'e' per nessuna)
    assert.equal(await s.page.getByRole('button', { name: 'Nuovo mob' }).count(), 0)
    assert.equal((await ro.call('PUT', `/api/mobs/${corrupted.id}`, { level: 3 })).status, 409)
    assert.equal((await rw.call('PUT', `/api/mobs/${corrupted.id}`, { level: 3 })).status, 409)
    assert.equal((await rw.call('DELETE', `/api/mobs/${corrupted.id}`)).status, 409)
  })

  it('maestri da spec_assign.c: filtro «Insegna / gain», colonna «Procedura speciale», API coerente', async () => {
    const trainers = (await ro.get('/api/mobs?trainer=true&pageSize=100')).data as { total: number; items: { vnum: number; isTrainer: boolean; extra: Record<string, string> }[] }
    assert.ok(trainers.total >= 27 && trainers.items.some((m) => m.vnum === 691)) // 26 *GuildMaster + monk_master (Cain) + altri maestri
    assert.ok(trainers.items.every((m) => m.isTrainer && /guildmaster|monk_master/i.test(m.extra.specProc ?? '')))
    const others = (await ro.get('/api/mobs?trainer=false&pageSize=100')).data as { items: { isTrainer: boolean }[] }
    assert.ok(others.items.every((m) => m.isTrainer === false))
    await goto(s.page, '/mobs?trainer=true')
    await s.page.locator('[data-test="tri-trainer"]').waitFor()
    await s.page.locator('[data-test="active-filters"] .q-chip', { hasText: 'Insegna / gain: Sì' }).waitFor()
    const columns = s.page.locator('[data-test="columns-menu"]')
    await columns.click()
    await s.page.locator('.q-menu .q-item', { hasText: 'Procedura speciale' }).click()
    await s.page.locator('.q-menu .q-item', { hasText: 'Insegna' }).click()
    await s.page.keyboard.press('Escape')
    await s.page.locator('td', { hasText: 'MageGuildMaster' }).first().waitFor()
    await s.page.locator('[data-test="trainer-chip"]').first().waitFor()
    assert.equal(await rawI18nKey(s.page), null)
    await columns.click()
    await s.page.locator('.q-menu .q-item', { hasText: 'Ripristina' }).click()
    await s.page.keyboard.press('Escape')
  })

  it('sola lettura: le scritture sono rifiutate', async () => {
    assert.equal((await ro.call('PUT', '/api/mobs/1', { level: 3 })).status, 409)
    assert.equal((await ro.call('PUT', '/api/rooms/1', { name: 'x' })).status, 409)
    assert.equal((await ro.call('DELETE', '/api/rooms/1')).status, 409)
  })

  it('script di reset: ifValue negativo, commenti e comandi 7-10 con etichette localizzate', async () => {
    await goto(s.page, '/zones/2/resets')
    await s.page.locator('[data-test="reset-if-value"]').first().waitFor()
    const values = await s.page.locator('input[data-test="reset-if-value"]').evaluateAll((els) => els.map((el) => (el as HTMLInputElement).value))
    assert.ok(values.filter((v) => v === '-5').length >= 13, `-5: ${values.length}`)
    // con il tipo di comando 7 (charm) gli argomenti hanno le etichette di Diku Modificato
    const first = s.page.locator('.pachi-zone-reset-item').first()
    await first.locator('.q-select').first().click()
    const options = await s.page.locator('.q-menu .q-item').allInnerTexts()
    for (const label of ['Charma un mob', 'Imposta odio', 'Imposta paura', 'Imposta la zona di un mob']) assert.ok(options.includes(label), label)
    await s.page.locator('.q-menu .q-item', { hasText: 'Imposta la zona di un mob' }).click()
    await first.getByLabel('Zona', { exact: true }).waitFor()
    await first.getByLabel('Flag', { exact: true }).waitFor()
    assert.equal(await rawI18nKey(s.page), null)
    await goto(s.page, '/') // il passo modificato resta non salvato: via con un caricamento completo
  })

  it('dikumod-rw: modifica una stanza, cambia solo quella', async () => {
    const rooms = await snapshot(rw, '/api/rooms')
    const mobs = await snapshot(rw, '/api/mobs')
    const objects = await snapshot(rw, '/api/objects')
    await pickWorld(s, 'Diku Modificato (scrivibile)')
    await goto(s.page, '/rooms?zoneId=1&roomId=1')
    await s.page.getByLabel('Nome *').waitFor()
    assert.equal(await s.page.getByLabel('Nome *').inputValue(), 'Limbo')
    await s.page.getByLabel('Nome *').fill('Limbo di prova')
    await saveForm(s.page)
    assert.equal((await rw.get('/api/rooms/1')).data.name, 'Limbo di prova')
    assert.deepEqual(changedIds(rooms, await snapshot(rw, '/api/rooms')), [1])
    assert.deepEqual(changedIds(mobs, await snapshot(rw, '/api/mobs')), [])
    assert.deepEqual(changedIds(objects, await snapshot(rw, '/api/objects')), [])
    // la copia di sola lettura non e' cambiata
    assert.equal((await ro.get('/api/rooms/1')).data.name, 'Limbo')
  })

  it('dikumod-rw: modifica un mob (campo base ed extra), cambia solo quel mob', async () => {
    const rooms = await snapshot(rw, '/api/rooms')
    const mobs = await snapshot(rw, '/api/mobs')
    await goto(s.page, '/mobs?zoneId=1&mobId=1')
    await s.page.getByLabel('Descrizione breve *').waitFor()
    // campi senza equivalente in Diku Modificato: disabilitati
    await s.page.getByText('Ruoli e servizi').click()
    assert.equal(await s.page.getByLabel('Classe', { exact: true }).isDisabled(), true)
    await s.page.getByLabel('Descrizione breve *').fill('Puff il drago')
    await s.page.getByText('Campi specifici del mondo').click()
    await s.page.getByLabel('Esperienza grezza (negativa = fissa)').fill('123')
    await saveForm(s.page)
    const mob = (await rw.get('/api/mobs/1')).data
    assert.equal(mob.shortDescription, 'Puff il drago')
    assert.equal(mob.extra.expRaw, 123)
    assert.deepEqual(changedIds(mobs, await snapshot(rw, '/api/mobs')), [1])
    assert.deepEqual(changedIds(rooms, await snapshot(rw, '/api/rooms')), [])
  })

  it('dikumod-rw: lo script di reset salvato conserva ifValue e commenti', async () => {
    const before = (await rw.get('/api/zones/1/reset-commands')).data as { ifValue: number; comment: string | null; commandType: number }[]
    assert.ok(before.some((c) => c.comment))
    await goto(s.page, '/zones/1/resets')
    await s.page.locator('input[data-test="reset-comment"]').first().waitFor()
    await s.page.locator('input[data-test="reset-comment"]').first().fill('commento e2e')
    await s.page.getByRole('button', { name: 'Salva script' }).click()
    await s.page.getByText('Script di reset salvato').first().waitFor()
    const after = (await rw.get('/api/zones/1/reset-commands')).data as typeof before
    assert.equal(after.length, before.length)
    assert.equal(after[0]!.comment, 'commento e2e')
    assert.deepEqual(after.map((c) => c.ifValue), before.map((c) => c.ifValue))
    assert.deepEqual(after.slice(1).map((c) => c.comment), before.slice(1).map((c) => c.comment))
  })

  it('nessun errore di console inatteso', async () => {
    s.allow(/409/)
    assert.deepEqual(s.errors.filter((e) => !/409/.test(e)), [])
    await pickWorld(s, 'Pachimud')
  })
})
