/** Stanze: creazione con uscite ed extra description, modifica, clonazione, eliminazione e mappa. */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import type { Locator } from 'playwright-core'
import { Api } from '../support/api.ts'
import { addFlag, closeDiscarding, confirm, dialog, dismissError, goto, loginOk, openDetail, openSession, pickOption, rawI18nKey, saveDialog, saveForm, tableRow, type Session, waitDialogsClosed } from '../support/browser.ts'

/** Vnum creati dai test (puliti all'avvio e alla fine). */
const VNUMS = [1010, 1011, 1012, 1070, 1071, 1072, 1073, 1074, 2070]

/** Elimina via API le stanze di test rimaste (uscite/extra vanno con la stanza). */
async function cleanup(api: Api): Promise<void> {
  for (const vnum of VNUMS) {
    const room = await api.byVnum('rooms', vnum)
    if (room) await api.call('DELETE', `/api/rooms/${room.id}`)
  }
}

/** Stanze per i test di filtri e ordinamenti: recupero PF distinto e riconoscibile (>= 7770). */
const STAT_ROOMS = [
  { vnum: 1070, zone: 10, name: 'Stat alfa', healRate: 7772, sectorType: 3 },
  { vnum: 1071, zone: 10, name: 'Stat beta', healRate: 7771, sectorType: 1 },
  { vnum: 1072, zone: 10, name: 'Stat gamma', healRate: 7773, sectorType: 3 },
  { vnum: 2070, zone: 20, name: 'Stat delta', healRate: 7774, sectorType: 1 },
]

/** Nomi delle righe visibili con prefisso `Stat`, nell'ordine mostrato. */
async function statRows(page: Session['page']): Promise<string[]> {
  await page.waitForLoadState('networkidle')
  const texts = await page.locator('table tbody tr').allInnerTexts()
  return texts.map((text) => /Stat \w+/.exec(text)?.[0] ?? '').filter(Boolean)
}

describe('stanze', () => {
  let s: Session
  let api: Api

  before(async () => {
    api = await Api.connect()
    await cleanup(api)
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await s.close()
    await cleanup(api)
  })

  it('la lista mostra le stanze', async () => {
    await goto(s.page, '/rooms')
    for (const name of ['Piazza', 'Vicolo', 'Cantina']) await tableRow(s.page, name).waitFor()
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('di default mostra le stanze di tutte le zone, con colonne delle statistiche', async () => {
    for (const r of STAT_ROOMS) {
      const zone = await api.byVnum('zones', r.zone)
      const res = await api.call('POST', '/api/rooms', {
        vnum: r.vnum,
        zoneId: zone.id,
        name: r.name,
        healRate: r.healRate,
        sectorType: r.sectorType,
      })
      assert.equal(res.status, 201)
    }
    await goto(s.page, '/rooms?minHealRate=7770')
    await tableRow(s.page, 'Stat delta').waitFor()
    await tableRow(s.page, 'Stat alfa').waitFor()
    for (const header of ['Terreno', 'Zona', 'Recupero PF %']) assert.equal(await s.page.locator('th', { hasText: header }).count(), 1, header)
    await tableRow(s.page, 'Stat delta').getByText('Zona Vuota').waitFor()
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('ordina per recupero PF lato server (asc poi desc)', async () => {
    await goto(s.page, '/rooms?minHealRate=7770')
    await tableRow(s.page, 'Stat alfa').waitFor()
    const header = s.page.locator('th', { hasText: 'Recupero PF %' })
    await Promise.all([s.page.waitForResponse((r) => /orderBy=healRate(&|$)/.test(r.url())), header.click()])
    assert.deepEqual(await statRows(s.page), ['Stat beta', 'Stat alfa', 'Stat gamma', 'Stat delta'])
    await Promise.all([s.page.waitForResponse((r) => /orderBy=-healRate/.test(r.url())), header.click()])
    assert.deepEqual(await statRows(s.page), ['Stat delta', 'Stat gamma', 'Stat alfa', 'Stat beta'])
  })

  it('filtra per terreno e intervallo; i filtri sono nell URL, nei chip e si azzerano', async () => {
    await goto(s.page, '/rooms?minHealRate=7770')
    await tableRow(s.page, 'Stat alfa').waitFor()
    await pickOption(s.page, 'Terreno', 'Foresta')
    await s.page.keyboard.press('Escape')
    await s.page.getByLabel('Recupero PF % max').fill('7772')
    await tableRow(s.page, 'Stat gamma').waitFor({ state: 'detached' })
    assert.deepEqual(await statRows(s.page), ['Stat alfa'])
    const url = new URL(s.page.url())
    assert.equal(url.searchParams.get('sectorType'), '3')
    assert.equal(url.searchParams.get('minHealRate'), '7770')
    assert.equal(url.searchParams.get('maxHealRate'), '7772')
    await s.page.locator('[data-test="active-filters"] .q-chip', { hasText: 'Terreno: Foresta' }).waitFor()
    // ricaricando l'URL lo stato si ripristina
    await goto(s.page, `${url.pathname}${url.search}`)
    await s.page.locator('[data-test="active-filters"] .q-chip', { hasText: 'Recupero PF %' }).waitFor()
    assert.deepEqual(await statRows(s.page), ['Stat alfa'])
    await s.page.getByRole('button', { name: 'Azzera filtri' }).click()
    await s.page.waitForLoadState('networkidle')
    assert.equal(new URL(s.page.url()).search, '')
    assert.equal(await s.page.locator('[data-test="active-filters"]').count(), 0)
  })

  it('mostra e nasconde le colonne, la scelta resta salvata', async () => {
    await goto(s.page, '/rooms?minHealRate=7770')
    await tableRow(s.page, 'Stat alfa').waitFor()
    assert.equal(await s.page.locator('th', { hasText: 'Proprietario' }).count(), 0)
    await s.page.getByRole('button', { name: 'Colonne' }).click()
    await s.page.locator('.q-menu .q-item', { hasText: 'Proprietario' }).click()
    await s.page.locator('th', { hasText: 'Proprietario' }).waitFor()
    await s.page.locator('.q-menu .q-item', { hasText: 'Recupero Mana %' }).click()
    assert.equal(await s.page.locator('th', { hasText: 'Recupero Mana %' }).count(), 0)
    await s.page.keyboard.press('Escape')
    await goto(s.page, '/rooms?minHealRate=7770')
    await s.page.locator('th', { hasText: 'Proprietario' }).waitFor()
    assert.equal(await s.page.locator('th', { hasText: 'Recupero Mana %' }).count(), 0)
    await s.page.getByRole('button', { name: 'Colonne' }).click()
    await s.page.locator('.q-menu .q-item', { hasText: 'Ripristina' }).click()
    await s.page.locator('th', { hasText: 'Recupero Mana %' }).waitFor()
  })

  it('con una zona scelta la lista e la creazione restano per zona; la mappa segue la zona', async () => {
    const zone = await api.byVnum('zones', 20)
    await goto(s.page, `/rooms?zoneId=${zone.id}`)
    await tableRow(s.page, 'Stat delta').waitFor()
    assert.equal(await tableRow(s.page, 'Stat alfa').count(), 0)
    assert.match(await s.page.getByRole('link', { name: 'Mappa' }).getAttribute('href') ?? '', new RegExp(`zoneId=${zone.id}`))
    await s.page.getByRole('button', { name: 'Nuova stanza' }).click()
    // zona gia' scelta: niente richiesta, si apre direttamente il form
    await s.page.getByLabel('Nome *').waitFor()
    await s.page.getByLabel('Chiudi').first().click()
    await waitDialogsClosed(s.page)
  })

  it('a 375 px filtri e tabella restano nello schermo', async () => {
    await s.page.setViewportSize({ width: 375, height: 800 })
    await goto(s.page, '/rooms?minHealRate=7770')
    await tableRow(s.page, 'Stat alfa').waitFor()
    const overflow = await s.page.evaluate(() => ({
      tables: [...document.querySelectorAll('.q-table__container')].map((e) => e.getBoundingClientRect().right),
      scroll: document.documentElement.scrollWidth,
      width: innerWidth,
    }))
    for (const right of overflow.tables) assert.ok(right <= overflow.width, `tabella oltre lo schermo (${right})`)
    assert.ok(overflow.scroll <= overflow.width, 'la pagina scorre in orizzontale')
    await s.page.setViewportSize({ width: 1400, height: 1000 })
  })

  it('crea una stanza con flag, uscita ed extra description', async () => {
    await goto(s.page, '/rooms')
    await s.page.getByRole('button', { name: 'Nuova stanza' }).click()
    // con «Tutte le zone» la creazione chiede prima la zona
    await pickOption(s.page, 'Zona di destinazione', 'Zona Alfa')
    await s.page.getByRole('button', { name: 'Continua' }).click()
    await s.page.getByLabel('Vnum *', { exact: true }).fill('1010')
    await s.page.getByLabel('Nome *').fill('Sala Pw')
    await s.page.getByLabel('Descrizione').fill('Una sala di prova.')
    await addFlag(s.page, 'Flag (digita e invio)', 'DARK')
    await dialog(s.page).locator('.q-chip', { hasText: 'DARK' }).waitFor()
    // uscita a nord verso la Piazza
    const north = dialog(s.page).locator('tr', { hasText: 'Nord' })
    await north.locator('.q-checkbox').first().click()
    await north.locator('.q-select').first().click()
    await s.page.locator('.q-menu .q-item', { hasText: 'Piazza' }).first().click()
    // extra description
    await dialog(s.page).getByRole('button', { name: /Aggiungi extra description/i }).click()
    await dialog(s.page).getByLabel('Parole chiave', { exact: true }).fill('tavolo')
    await dialog(s.page).getByLabel('Testo').fill('Un tavolo di legno.')
    await saveDialog(s.page)
    await waitDialogsClosed(s.page)
    await tableRow(s.page, 'Sala Pw').waitFor()

    const room = await api.byVnum('rooms', 1010)
    const detail = (await api.get(`/api/rooms/${room.id}`)).data
    assert.deepEqual(detail.flags, ['DARK'])
    assert.equal(detail.exits.length, 1)
    assert.equal(detail.exits[0].direction, 0)
    assert.equal(detail.exits[0].targetRoomVnum, 1000)
    assert.deepEqual(
      detail.extraDescriptions.map((e: any) => [e.keywords, e.text]),
      [['tavolo', 'Un tavolo di legno.']],
    )
  })

  it('vnum duplicato: errore tradotto', async () => {
    s.allow(/409/)
    await s.page.getByRole('button', { name: 'Nuova stanza' }).click()
    await pickOption(s.page, 'Zona di destinazione', 'Zona Alfa')
    await s.page.getByRole('button', { name: 'Continua' }).click()
    await s.page.getByLabel('Vnum *', { exact: true }).fill('1000')
    await s.page.getByLabel('Nome *').fill('Doppia')
    await saveDialog(s.page)
    await s.page.locator('.q-notification', { hasText: 'Esiste già una stanza con vnum 1000' }).waitFor()
    assert.equal(await rawI18nKey(s.page), null)
    await closeDiscarding(s.page)
  })

  it('riapre la stanza: chip, uscita ed extra description sono persistiti; la modifica si salva', async () => {
    await openDetail(s.page, tableRow(s.page, 'Sala Pw'))
    await s.page.locator('.q-chip', { hasText: 'DARK' }).waitFor()
    assert.equal(await s.page.getByLabel('Parole chiave', { exact: true }).inputValue(), 'tavolo')
    await s.page.getByLabel('Nome *').fill('Sala Pw modificata')
    await addFlag(s.page, 'Flag (digita e invio)', 'NO_MOB')
    await saveForm(s.page)
    // `saveForm` puo' vedere la notifica positiva del test precedente (dura 5 s): si attende la fine vera del salvataggio (titolo ricaricato)
    await s.page.getByRole('heading', { name: /Sala Pw modificata/ }).waitFor()
    await s.page.getByLabel("Torna all'elenco").click()
    await tableRow(s.page, 'Sala Pw modificata').waitFor()
    const room = await api.byVnum('rooms', 1010)
    assert.equal(room.name, 'Sala Pw modificata')
    assert.deepEqual(room.flags, ['DARK', 'NO_MOB'])
  })

  it('clima della stanza: si imposta, vuoto = eredita dalla zona, un valore errato e rifiutato', async () => {
    s.allow(/422/)
    const room = await api.byVnum('rooms', 1010)
    assert.equal((await api.get(`/api/rooms/${room.id}`)).data.extra.climate, null)
    assert.equal((await api.call('PUT', `/api/rooms/${room.id}`, { extra: { climate: 'desert' } })).data.extra.climate, 'desert')
    assert.equal((await api.call('PUT', `/api/rooms/${room.id}`, { extra: { climate: 'tropicale' } })).status, 422)
    assert.equal((await api.call('PUT', `/api/rooms/${room.id}`, { extra: { climate: '' } })).data.extra.climate, null)
  })

  it('clima della stanza: il form mostra quale clima eredita dalla zona se il campo è vuoto', async () => {
    await openDetail(s.page, tableRow(s.page, 'Sala Pw modificata'))
    await s.page.getByText('Campi specifici del mondo').click()
    await s.page.getByText('eredita il clima della zona: Temperato').waitFor()
    await s.page.getByLabel("Torna all'elenco").click()
    await tableRow(s.page, 'Sala Pw modificata').waitFor()
    // con la zona nel deserto l'hint cambia
    const zone = await api.byVnum('zones', 10)
    await api.call('PUT', `/api/zones/${zone.id}`, { extra: { climate: 'desert' } })
    try {
      await openDetail(s.page, tableRow(s.page, 'Sala Pw modificata'))
      await s.page.getByText('Campi specifici del mondo').click()
      await s.page.getByText('eredita il clima della zona: Deserto').waitFor()
    } finally {
      await api.call('PUT', `/api/zones/${zone.id}`, { extra: { climate: 'temperate' } })
    }
    await s.page.getByLabel("Torna all'elenco").click()
    await tableRow(s.page, 'Sala Pw modificata').waitFor()
  })

  it('porta modificata dal dettaglio: «applica anche al ritorno» la copia sull\'uscita opposta (e senza spunta no)', async () => {
    const zone = await api.byVnum('zones', 10)
    const [a, b] = [1073, 1074].map((vnum) => ({ vnum, zoneId: zone.id, name: `Porta ${vnum}`, description: 'x', sectorType: 1 }))
    const idA = (await api.call('POST', '/api/rooms', a)).data.id
    const idB = (await api.call('POST', '/api/rooms', b)).data.id
    await api.call('POST', `/api/rooms/${idA}/exits`, { direction: 0, targetRoomId: idB })
    await api.call('POST', `/api/rooms/${idB}/exits`, { direction: 2, targetRoomId: idA })
    const exitOf = async (id: number): Promise<any> => (await api.get(`/api/rooms/${id}`)).data.exits[0]
    const north = (): Locator => s.page.locator('tr', { hasText: 'Nord' }).first()
    const setMirror = async (on: boolean): Promise<void> => {
      const box = s.page.getByTestId('exits-mirror')
      if ((await box.getAttribute('aria-checked')) !== String(on)) await box.click()
    }
    await goto(s.page, `/rooms/${idA}`)
    // senza spunta: cambia solo l'andata
    await north().locator('.q-select').nth(1).click()
    await s.page.locator('.q-menu .q-item', { hasText: /chiudibile|closable/i }).first().click()
    await setMirror(false)
    await saveForm(s.page)
    assert.equal((await exitOf(idA)).doorFlag, 1)
    assert.equal((await exitOf(idB)).doorFlag, 0)
    // con la spunta (default): porta, stato e parole chiave arrivano anche al ritorno
    await s.page.getByRole('heading', { name: /Porta 1073/ }).waitFor()
    await s.page.getByLabel('Parole chiave porta').first().fill('porta')
    await setMirror(true)
    await saveForm(s.page)
    await s.page.waitForTimeout(500)
    assert.equal((await exitOf(idB)).doorFlag, 1)
    assert.equal((await exitOf(idB)).keywords, 'porta')
    await goto(s.page, '/rooms') // i test seguenti partono dall'elenco
  })

  it('clona la stanza (extra copiate, uscite no)', async () => {
    await tableRow(s.page, 'Sala Pw modificata').locator('td.q-td button').filter({ hasNot: s.page.locator('.pachi-t2-edit-item') }).first().click()
    await s.page.getByLabel('Nuovo vnum *').fill('1011')
    await s.page.getByLabel('Nuovo nome (opzionale)').fill('Sala clonata')
    await saveDialog(s.page)
    await waitDialogsClosed(s.page)
    await tableRow(s.page, 'Sala clonata').waitFor()
    const clone = await api.byVnum('rooms', 1011)
    const detail = (await api.get(`/api/rooms/${clone.id}`)).data
    assert.equal(detail.exits.length, 0)
    assert.equal(detail.extraDescriptions.length, 1)
  })

  it('eliminare una stanza usata da un reset e rifiutato', async () => {
    s.allow(/409/)
    await tableRow(s.page, 'Piazza').locator('.text-negative').click()
    await s.page.getByText(/referenziata da 2 comandi di reset/).first().waitFor() // avviso preventivo
    await confirm(s.page)
    await s.page.getByText(/Impossibile eliminare: la stanza è referenziata da 2 comandi di reset/).waitFor()
    await dismissError(s.page)
    assert.ok(await api.byVnum('rooms', 1000))
  })

  it('la mappa mostra i nodi della zona', async () => {
    await goto(s.page, '/rooms/map')
    const nodes = s.page.locator('.pachi-room-node')
    await nodes.first().waitFor()
    await s.page.locator('.pachi-room-node', { hasText: 'Piazza' }).waitFor()
    await s.page.locator('.pachi-room-node', { hasText: 'Sala Pw modificata' }).waitFor()
    assert.ok((await nodes.count()) >= 5)
    assert.ok((await s.page.locator('.vue-flow__edge').count()) >= 1)
    assert.equal(await rawI18nKey(s.page), null)
    // un clic su un nodo apre il pannello della stanza, da cui si apre l'editor
    await s.page.locator('.pachi-room-node', { hasText: 'Vicolo' }).click()
    await s.page.getByTestId('map-open-room').click()
    await s.page.getByLabel('Nome *').first().waitFor()
    assert.equal(await s.page.getByLabel('Nome *').first().inputValue(), 'Vicolo')
  })

  it('elimina le stanze create dal test', async () => {
    await goto(s.page, '/rooms')
    for (const name of ['Sala clonata', 'Sala Pw modificata']) {
      await tableRow(s.page, name).locator('.text-negative').click()
      await confirm(s.page)
      await tableRow(s.page, name).waitFor({ state: 'detached' })
    }
    assert.equal(await api.byVnum('rooms', 1010), undefined)
    assert.equal(await api.byVnum('rooms', 1011), undefined)
  })

  it('nessun errore di console imprevisto', () => {
    assert.deepEqual(s.errors, [])
  })
})
