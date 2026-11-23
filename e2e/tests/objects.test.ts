/** Oggetti: CRUD dall'interfaccia, flag (extra e wear) creati con Invio e persistiti, errori tradotti. */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import { addFlag, closeDiscarding, confirm, dialog, dismissError, goto, loginOk, openDetail, openSession, pickOption, rawI18nKey, saveDialog, saveForm, tableRow, type Session, waitDialogsClosed } from '../support/browser.ts'

/** Vnum creati dai test. */
const VNUMS = [1060, 1061, 1062, 1063, 1064, 2062]

/** Elimina via API gli oggetti di test rimasti. */
async function cleanup(api: Api): Promise<void> {
  for (const vnum of VNUMS) {
    const obj = await api.byVnum('objects', vnum)
    if (obj) await api.call('DELETE', `/api/objects/${obj.id}`)
  }
}

/** Oggetti per i test di filtri e ordinamenti: costo/tipo distinti e riconoscibili (costo >= 777000). */
const STAT_OBJECTS = [
  { vnum: 1062, zone: 10, desc: 'stat alfa', objectType: 1, cost: 777002, weight: 5 },
  { vnum: 1063, zone: 10, desc: 'stat beta', objectType: 2, cost: 777001, weight: 9 },
  { vnum: 1064, zone: 10, desc: 'stat gamma', objectType: 1, cost: 777003, weight: 7 },
  { vnum: 2062, zone: 20, desc: 'stat delta', objectType: 2, cost: 777004, weight: 1 },
]

/** Descrizioni delle righe visibili con prefisso `stat`, nell'ordine mostrato. */
async function statRows(page: Session['page']): Promise<string[]> {
  await page.waitForLoadState('networkidle')
  const texts = await page.locator('table tbody tr').allInnerTexts()
  return texts.map((text) => /stat \w+/.exec(text)?.[0] ?? '').filter(Boolean)
}

/** Apre il dialog di creazione scegliendo la zona (con «Tutte le zone» la lista la chiede prima). */
async function openCreate(page: Session['page'], zoneName: string): Promise<void> {
  await page.getByRole('button', { name: 'Nuovo oggetto' }).click()
  await pickOption(page, 'Zona di destinazione', zoneName)
  await page.getByRole('button', { name: 'Continua' }).click()
}

describe('oggetti', () => {
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

  it('la lista mostra gli oggetti della zona', async () => {
    await goto(s.page, '/objects')
    await tableRow(s.page, 'una spada').waitFor()
    await tableRow(s.page, 'un sasso').waitFor()
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('di default mostra gli oggetti di tutte le zone, con colonne delle statistiche', async () => {
    for (const o of STAT_OBJECTS) {
      const zone = await api.byVnum('zones', o.zone)
      const res = await api.call('POST', '/api/objects', {
        vnum: o.vnum,
        zoneId: zone.id,
        keywords: 'stat',
        shortDescription: o.desc,
        objectType: o.objectType,
        cost: o.cost,
        weight: o.weight,
      })
      assert.equal(res.status, 201)
    }
    await goto(s.page, '/objects?minCost=777000')
    await s.page.getByLabel('Zona', { exact: true }).waitFor()
    assert.match(await s.page.getByLabel('Zona', { exact: true }).innerText().catch(() => 'Tutte le zone'), /Tutte le zone|^$/)
    await tableRow(s.page, 'stat delta').waitFor()
    await tableRow(s.page, 'stat alfa').waitFor()
    assert.equal(await s.page.locator('th', { hasText: 'Costo' }).count(), 1)
    assert.equal(await s.page.locator('th', { hasText: 'Zona' }).count(), 1)
    await tableRow(s.page, 'stat delta').getByText('Zona Vuota').waitFor()
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('ordina per costo lato server (asc poi desc)', async () => {
    await goto(s.page, '/objects?minCost=777000')
    await tableRow(s.page, 'stat alfa').waitFor()
    const header = s.page.locator('th', { hasText: 'Costo' })
    await Promise.all([s.page.waitForResponse((r) => /orderBy=cost(&|$)/.test(r.url())), header.click()])
    assert.deepEqual(await statRows(s.page), ['stat beta', 'stat alfa', 'stat gamma', 'stat delta'])
    await Promise.all([s.page.waitForResponse((r) => /orderBy=-cost/.test(r.url())), header.click()])
    assert.deepEqual(await statRows(s.page), ['stat delta', 'stat gamma', 'stat alfa', 'stat beta'])
  })

  it('filtra per tipo e intervallo di costo; i filtri sono nell URL, nei chip e si azzerano', async () => {
    await goto(s.page, '/objects?minCost=777000')
    await tableRow(s.page, 'stat alfa').waitFor()
    await pickOption(s.page, 'Tipo', 'Arma')
    await s.page.keyboard.press('Escape')
    await s.page.getByLabel('Costo max').fill('777002')
    await tableRow(s.page, 'stat gamma').waitFor({ state: 'detached' })
    assert.deepEqual((await statRows(s.page)).sort(), ['stat alfa'])
    const url = new URL(s.page.url())
    assert.equal(url.searchParams.get('objectType'), '1')
    assert.equal(url.searchParams.get('minCost'), '777000')
    assert.equal(url.searchParams.get('maxCost'), '777002')
    await s.page.locator('[data-test="active-filters"] .q-chip', { hasText: 'Tipo: Arma' }).waitFor()
    // ricaricando l'URL lo stato si ripristina
    await goto(s.page, `${url.pathname}${url.search}`)
    await s.page.locator('[data-test="active-filters"] .q-chip', { hasText: 'Costo' }).waitFor()
    assert.deepEqual(await statRows(s.page), ['stat alfa'])
    await s.page.getByRole('button', { name: 'Azzera filtri' }).click()
    await s.page.waitForLoadState('networkidle')
    assert.equal(new URL(s.page.url()).search, '')
    await tableRow(s.page, 'stat delta').waitFor({ state: 'detached', timeout: 100 }).catch(() => undefined)
    assert.equal(await s.page.locator('[data-test="active-filters"]').count(), 0)
  })

  it('mostra e nasconde le colonne, la scelta resta salvata', async () => {
    await goto(s.page, '/objects?minCost=777000')
    await tableRow(s.page, 'stat alfa').waitFor()
    assert.equal(await s.page.locator('th', { hasText: 'Valore 1' }).count(), 0)
    await s.page.getByRole('button', { name: 'Colonne' }).click()
    await s.page.locator('.q-menu .q-item', { hasText: 'Valore 1' }).click()
    await s.page.locator('th', { hasText: 'Valore 1' }).waitFor()
    await s.page.locator('.q-menu .q-item', { hasText: 'Peso' }).click()
    assert.equal(await s.page.locator('th', { hasText: 'Peso' }).count(), 0)
    await s.page.keyboard.press('Escape')
    await goto(s.page, '/objects?minCost=777000')
    await s.page.locator('th', { hasText: 'Valore 1' }).waitFor()
    assert.equal(await s.page.locator('th', { hasText: 'Peso' }).count(), 0)
    await s.page.getByRole('button', { name: 'Colonne' }).click()
    await s.page.locator('.q-menu .q-item', { hasText: 'Ripristina' }).click()
    await s.page.locator('th', { hasText: 'Peso' }).waitFor()
  })

  it('con una zona scelta la lista e la creazione restano per zona', async () => {
    const zone = await api.byVnum('zones', 20)
    await goto(s.page, `/objects?zoneId=${zone.id}`)
    await tableRow(s.page, 'stat delta').waitFor()
    assert.equal(await tableRow(s.page, 'stat alfa').count(), 0)
    await s.page.getByRole('button', { name: 'Nuovo oggetto' }).click()
    // zona gia' scelta: niente richiesta, si apre direttamente il form
    await s.page.getByLabel('Descrizione breve *').waitFor()
    await s.page.getByLabel('Chiudi').first().click()
    await waitDialogsClosed(s.page)
  })

  it('pachimud: i flag vengono dal catalogo del gioco, con descrizione e «non ancora attivo»', async () => {
    await goto(s.page, '/objects')
    await openCreate(s.page, 'Zona Alfa')
    const input = s.page.getByLabel('Extra flag (digita e invio)')
    await input.click()
    await input.fill('ANTI_S')
    const option = s.page.getByTestId('flag-option-ANTI_SUN')
    await option.waitFor()
    await option.getByText('non ancora attivo').waitFor()
    await option.getByText('Soffre la luce del sole.').waitFor()
    await s.page.keyboard.press('Escape')
    await s.page.keyboard.press('Escape')
    await waitDialogsClosed(s.page)
  })

  it('crea un oggetto con extra e wear flag (chip con Invio)', async () => {
    await goto(s.page, '/objects')
    await openCreate(s.page, 'Zona Alfa')
    await s.page.getByLabel('Vnum', { exact: true }).fill('1060')
    await s.page.getByLabel('Parole chiave *').fill('elmo ferro')
    await s.page.getByLabel('Descrizione breve *').fill('un elmo di ferro')
    await dialog(s.page).getByLabel('Peso').fill('7')
    await addFlag(s.page, 'Extra flag (digita e invio)', 'GLOW')
    await addFlag(s.page, 'Extra flag (digita e invio)', 'MAGIC')
    await addFlag(s.page, 'Wear flag (digita e invio)', 'HEAD')
    await dialog(s.page).locator('.q-chip', { hasText: 'GLOW' }).waitFor()
    await dialog(s.page).locator('.q-chip', { hasText: 'MAGIC' }).waitFor()
    await dialog(s.page).locator('.q-chip', { hasText: 'HEAD' }).waitFor()
    await saveDialog(s.page)
    await waitDialogsClosed(s.page)
    await tableRow(s.page, 'un elmo di ferro').waitFor()
    const obj = await api.byVnum('objects', 1060)
    assert.deepEqual(obj.extraFlags, ['GLOW', 'MAGIC'])
    assert.deepEqual(obj.wearFlags, ['HEAD'])
    assert.equal(obj.weight, 7)
  })

  it('vnum duplicato: errore tradotto', async () => {
    s.allow(/409/)
    await openCreate(s.page, 'Zona Alfa')
    await s.page.getByLabel('Vnum', { exact: true }).fill('1000')
    await s.page.getByLabel('Parole chiave *').fill('x')
    await s.page.getByLabel('Descrizione breve *').fill('doppio')
    await saveDialog(s.page)
    await s.page.locator('.q-notification', { hasText: 'Esiste già un oggetto con vnum 1000' }).waitFor()
    assert.equal(await rawI18nKey(s.page), null)
    await closeDiscarding(s.page)
  })

  it('modifica: i chip sono ricaricati, se ne aggiunge uno e si salva', async () => {
    await openDetail(s.page, tableRow(s.page, 'un elmo di ferro'))
    await s.page.locator('.q-chip', { hasText: 'GLOW' }).waitFor()
    await s.page.locator('.q-chip', { hasText: 'HEAD' }).waitFor()
    await addFlag(s.page, 'Wear flag (digita e invio)', 'WIELD')
    await s.page.getByLabel('Descrizione breve *').fill('un elmo di bronzo')
    await saveForm(s.page)
    await s.page.getByLabel("Torna all'elenco").click()
    await tableRow(s.page, 'un elmo di bronzo').waitFor()
    const obj = await api.byVnum('objects', 1060)
    assert.deepEqual(obj.extraFlags, ['GLOW', 'MAGIC'])
    assert.deepEqual(obj.wearFlags, ['HEAD', 'WIELD'])
    assert.equal(obj.shortDescription, 'un elmo di bronzo')
  })

  it('un oggetto usato da un reset non si elimina (409 tradotto)', async () => {
    s.allow(/409/)
    await tableRow(s.page, 'una spada').locator('.text-negative').click()
    await confirm(s.page)
    await s.page.getByText(/Impossibile eliminare: l'oggetto è referenziato da 1 comandi di reset/).waitFor()
    await dismissError(s.page)
    assert.ok(await api.byVnum('objects', 1000))
  })

  it("elimina l'oggetto creato", async () => {
    await tableRow(s.page, 'un elmo di bronzo').locator('.text-negative').click()
    await confirm(s.page)
    await tableRow(s.page, 'un elmo di bronzo').waitFor({ state: 'detached' })
    assert.equal(await api.byVnum('objects', 1060), undefined)
  })

  it('nessun errore di console imprevisto', () => {
    assert.deepEqual(s.errors, [])
  })
})
