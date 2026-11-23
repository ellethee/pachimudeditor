/** Mob: CRUD dall'interfaccia, flag creati con Invio e persistiti, errori tradotti. */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import { addFlag, closeDiscarding, confirm, dialog, dismissError, goto, loginOk, openDetail, openSession, pickOption, rawI18nKey, saveDialog, saveForm, tableRow, type Session, waitDialogsClosed } from '../support/browser.ts'

/** Vnum creati dai test. */
const VNUMS = [1050, 1051, 1062, 1063, 1064, 2062, 1065, 1066, 1067]

/** Elimina via API i mob di test rimasti. */
async function cleanup(api: Api): Promise<void> {
  for (const vnum of VNUMS) {
    const mob = await api.byVnum('mobs', vnum)
    if (mob) await api.call('DELETE', `/api/mobs/${mob.id}`)
  }
}

/** Mob per i test di filtri e ordinamenti: livello/sesso distinti e riconoscibili (livello >= 900). */
const STAT_MOBS = [
  { vnum: 1062, zone: 10, desc: 'stat alfa', level: 902, sex: 1, gold: 30 },
  { vnum: 1063, zone: 10, desc: 'stat beta', level: 901, sex: 2, gold: 20 },
  { vnum: 1064, zone: 10, desc: 'stat gamma', level: 903, sex: 1, gold: 10 },
  { vnum: 2062, zone: 20, desc: 'stat delta', level: 904, sex: 2, gold: 40 },
]

/** Descrizioni delle righe visibili con prefisso `stat`, nell'ordine mostrato. */
async function statRows(page: Session['page']): Promise<string[]> {
  await page.waitForLoadState('networkidle')
  const texts = await page.locator('table tbody tr').allInnerTexts()
  return texts.map((text) => /stat \w+/.exec(text)?.[0] ?? '').filter(Boolean)
}

/** Apre il dialog di creazione scegliendo la zona (con «Tutte le zone» la lista la chiede prima). */
async function openCreate(page: Session['page'], zoneName: string): Promise<void> {
  await page.getByRole('button', { name: 'Nuovo mob' }).click()
  await pickOption(page, 'Zona di destinazione', zoneName)
  await page.getByRole('button', { name: 'Continua' }).click()
}

describe('mob', () => {
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

  it('la lista mostra i mob', async () => {
    await goto(s.page, '/mobs')
    await tableRow(s.page, 'una guardia').waitFor()
    await tableRow(s.page, 'un ratto').waitFor()
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('di default mostra i mob di tutte le zone, con colonne delle statistiche', async () => {
    for (const m of STAT_MOBS) {
      const zone = await api.byVnum('zones', m.zone)
      const res = await api.call('POST', '/api/mobs', {
        vnum: m.vnum,
        zoneId: zone.id,
        keywords: 'stat',
        shortDescription: m.desc,
        level: m.level,
        sex: m.sex,
        gold: m.gold,
      })
      assert.equal(res.status, 201)
    }
    await goto(s.page, '/mobs?minLevel=900')
    await tableRow(s.page, 'stat delta').waitFor()
    await tableRow(s.page, 'stat alfa').waitFor()
    for (const header of ['Livello', 'Zona', 'Sesso', 'Oro']) assert.equal(await s.page.locator('th', { hasText: header }).count(), 1, header)
    await tableRow(s.page, 'stat delta').getByText('Zona Vuota').waitFor()
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('ordina per livello lato server (asc poi desc)', async () => {
    await goto(s.page, '/mobs?minLevel=900')
    await tableRow(s.page, 'stat alfa').waitFor()
    const header = s.page.locator('th', { hasText: 'Livello' })
    await Promise.all([s.page.waitForResponse((r) => /orderBy=level(&|$)/.test(r.url())), header.click()])
    assert.deepEqual(await statRows(s.page), ['stat beta', 'stat alfa', 'stat gamma', 'stat delta'])
    await Promise.all([s.page.waitForResponse((r) => /orderBy=-level/.test(r.url())), header.click()])
    assert.deepEqual(await statRows(s.page), ['stat delta', 'stat gamma', 'stat alfa', 'stat beta'])
  })

  it('filtra per sesso e intervallo di oro; i filtri sono nell URL, nei chip e si azzerano', async () => {
    await goto(s.page, '/mobs?minLevel=900')
    await tableRow(s.page, 'stat alfa').waitFor()
    await pickOption(s.page, 'Sesso', 'Maschio')
    await s.page.keyboard.press('Escape')
    await s.page.getByLabel('Oro max').fill('20')
    await tableRow(s.page, 'stat alfa').waitFor({ state: 'detached' })
    assert.deepEqual(await statRows(s.page), ['stat gamma'])
    const url = new URL(s.page.url())
    assert.equal(url.searchParams.get('sex'), '1')
    assert.equal(url.searchParams.get('minLevel'), '900')
    assert.equal(url.searchParams.get('maxGold'), '20')
    await s.page.locator('[data-test="active-filters"] .q-chip', { hasText: 'Sesso: Maschio' }).waitFor()
    // ricaricando l'URL lo stato si ripristina
    await goto(s.page, `${url.pathname}${url.search}`)
    await s.page.locator('[data-test="active-filters"] .q-chip', { hasText: 'Oro' }).waitFor()
    assert.deepEqual(await statRows(s.page), ['stat gamma'])
    await s.page.getByRole('button', { name: 'Azzera filtri' }).click()
    await s.page.waitForLoadState('networkidle')
    assert.equal(new URL(s.page.url()).search, '')
    assert.equal(await s.page.locator('[data-test="active-filters"]').count(), 0)
  })

  it('filtro Insegna / gain: tri-stato, chip, URL e colonna «Insegna»', async () => {
    const zone = await api.byVnum('zones', 10)
    for (const [vnum, desc, flags] of [
      [1065, 'stat maestro', ['guildmaster']],
      [1066, 'stat comune', ['sentinel']],
    ] as const) {
      const res = await api.call('POST', '/api/mobs', { vnum, zoneId: zone.id, keywords: 'stat', shortDescription: desc, level: 905, flags })
      assert.equal(res.status, 201)
    }
    await goto(s.page, '/mobs?minLevel=905')
    await tableRow(s.page, 'stat comune').waitFor()
    await tableRow(s.page, 'stat maestro').waitFor()
    const tri = s.page.locator('[data-test="tri-trainer"]')
    await tri.getByRole('button', { name: 'Sì' }).click()
    await tableRow(s.page, 'stat comune').waitFor({ state: 'detached' })
    assert.deepEqual(await statRows(s.page), ['stat maestro'])
    assert.equal(new URL(s.page.url()).searchParams.get('trainer'), 'true')
    await s.page.locator('[data-test="active-filters"] .q-chip', { hasText: 'Insegna / gain: Sì' }).waitFor()
    // l'URL ripristina il filtro; «No» mostra gli altri
    await goto(s.page, `/mobs?minLevel=905&trainer=true`)
    await tableRow(s.page, 'stat maestro').waitFor()
    assert.deepEqual(await statRows(s.page), ['stat maestro'])
    await s.page.locator('[data-test="tri-trainer"]').getByRole('button', { name: 'No' }).click()
    await tableRow(s.page, 'stat maestro').waitFor({ state: 'detached' })
    assert.deepEqual(await statRows(s.page), ['stat comune'])
    await s.page.locator('[data-test="tri-trainer"]').getByRole('button', { name: 'Tutti' }).click()
    await tableRow(s.page, 'stat maestro').waitFor()
    assert.equal(new URL(s.page.url()).searchParams.has('trainer'), false)
    // colonna «Insegna»: chip solo sul maestro; pachimud non ha «Procedura speciale»
    await s.page.locator('[data-test="columns-menu"]').click()
    assert.equal(await s.page.locator('.q-menu .q-item', { hasText: 'Procedura speciale' }).count(), 0)
    await s.page.locator('.q-menu .q-item', { hasText: 'Insegna' }).click()
    await s.page.keyboard.press('Escape')
    await tableRow(s.page, 'stat maestro').locator('[data-test="trainer-chip"]').waitFor()
    assert.equal(await tableRow(s.page, 'stat comune').locator('[data-test="trainer-chip"]').count(), 0)
    assert.equal(await rawI18nKey(s.page), null)
    await s.page.locator('[data-test="columns-menu"]').click()
    await s.page.locator('.q-menu .q-item', { hasText: 'Ripristina' }).click()
    await s.page.keyboard.press('Escape')
  })

  it('mostra e nasconde le colonne, la scelta resta salvata', async () => {
    await goto(s.page, '/mobs?minLevel=900')
    await tableRow(s.page, 'stat alfa').waitFor()
    assert.equal(await s.page.locator('th', { hasText: 'Esperienza' }).count(), 0)
    await s.page.getByRole('button', { name: 'Colonne' }).click()
    await s.page.locator('.q-menu .q-item', { hasText: 'Esperienza' }).click()
    await s.page.locator('th', { hasText: 'Esperienza' }).waitFor()
    await s.page.locator('.q-menu .q-item', { hasText: 'Oro' }).click()
    assert.equal(await s.page.locator('th', { hasText: 'Oro' }).count(), 0)
    await s.page.keyboard.press('Escape')
    await goto(s.page, '/mobs?minLevel=900')
    await s.page.locator('th', { hasText: 'Esperienza' }).waitFor()
    assert.equal(await s.page.locator('th', { hasText: 'Oro' }).count(), 0)
    await s.page.getByRole('button', { name: 'Colonne' }).click()
    await s.page.locator('.q-menu .q-item', { hasText: 'Ripristina' }).click()
    await s.page.locator('th', { hasText: 'Oro' }).waitFor()
  })

  it('con una zona scelta la lista e la creazione restano per zona', async () => {
    const zone = await api.byVnum('zones', 20)
    await goto(s.page, `/mobs?zoneId=${zone.id}`)
    await tableRow(s.page, 'stat delta').waitFor()
    assert.equal(await tableRow(s.page, 'stat alfa').count(), 0)
    await s.page.getByRole('button', { name: 'Nuovo mob' }).click()
    // zona gia' scelta: niente richiesta, si apre direttamente il form
    await s.page.getByLabel('Descrizione breve *').waitFor()
    await s.page.getByLabel('Chiudi').first().click()
    await waitDialogsClosed(s.page)
  })

  it('a 375 px filtri e tabella restano nello schermo', async () => {
    await s.page.setViewportSize({ width: 375, height: 800 })
    await goto(s.page, '/mobs?minLevel=900')
    await tableRow(s.page, 'stat alfa').waitFor()
    const overflow = await s.page.evaluate(() => ({
      tables: [...document.querySelectorAll('.q-table__container')].map((e) => e.getBoundingClientRect().right),
      scroll: document.documentElement.scrollWidth,
      width: innerWidth,
    }))
    for (const right of overflow.tables) assert.ok(right <= overflow.width, `tabella oltre lo schermo (${right})`)
    assert.ok(overflow.scroll <= overflow.width, 'la pagina scorre in orizzontale')
    await s.page.setViewportSize({ width: 1400, height: 1000 })
  })

  it('crea un mob con due flag (chip con Invio)', async () => {
    await goto(s.page, '/mobs')
    await openCreate(s.page, 'Zona Alfa')
    await s.page.getByLabel('Vnum', { exact: true }).fill('1050')
    await s.page.getByLabel('Parole chiave *').fill('goblin verde')
    await s.page.getByLabel('Descrizione breve *').fill('un goblin verde')
    await s.page.getByLabel('Livello', { exact: true }).fill('7')
    await addFlag(s.page, 'Flag (digita e invio)', 'SENTINEL')
    await addFlag(s.page, 'Flag (digita e invio)', 'AGGRESSIVE')
    await dialog(s.page).locator('.q-chip', { hasText: 'SENTINEL' }).waitFor()
    await dialog(s.page).locator('.q-chip', { hasText: 'AGGRESSIVE' }).waitFor()
    await saveDialog(s.page)
    await waitDialogsClosed(s.page)
    await tableRow(s.page, 'un goblin verde').waitFor()
    const mob = await api.byVnum('mobs', 1050)
    assert.deepEqual(mob.flags, ['SENTINEL', 'AGGRESSIVE'])
    assert.equal(mob.level, 7)
  })

  it('vnum duplicato: errore tradotto', async () => {
    s.allow(/409/)
    await openCreate(s.page, 'Zona Alfa')
    await s.page.getByLabel('Vnum', { exact: true }).fill('1000')
    await s.page.getByLabel('Parole chiave *').fill('x')
    await s.page.getByLabel('Descrizione breve *').fill('doppio')
    await saveDialog(s.page)
    await s.page.locator('.q-notification', { hasText: 'Esiste già un mob con vnum 1000' }).waitFor()
    assert.equal(await rawI18nKey(s.page), null)
    await closeDiscarding(s.page)
  })

  it('modifica: i chip sono ricaricati, se ne aggiunge uno e si salva', async () => {
    await openDetail(s.page, tableRow(s.page, 'un goblin verde'))
    await s.page.locator('.q-chip', { hasText: 'SENTINEL' }).waitFor()
    await s.page.locator('.q-chip', { hasText: 'AGGRESSIVE' }).waitFor()
    await addFlag(s.page, 'Flag (digita e invio)', 'SCAVENGER')
    await s.page.getByLabel('Descrizione breve *').fill('un goblin rosso')
    await saveForm(s.page)
    await s.page.getByLabel("Torna all'elenco").click()
    await tableRow(s.page, 'un goblin rosso').waitFor()
    const mob = await api.byVnum('mobs', 1050)
    assert.deepEqual(mob.flags, ['SENTINEL', 'AGGRESSIVE', 'SCAVENGER'])
    assert.equal(mob.shortDescription, 'un goblin rosso')
  })

  it('salvare senza toccare il campo opzionale non lo cancella; svuotarlo lo toglie', async () => {
    const zone = await api.byVnum('zones', 10)
    const res = await api.call('POST', '/api/mobs', { vnum: 1067, zoneId: zone.id, keywords: 'cieco', shortDescription: 'un mob cieco', debuffSkillId: 'curse' })
    assert.equal(res.status, 201)
    await goto(s.page, '/mobs')
    await openDetail(s.page, tableRow(s.page, 'un mob cieco'))
    await s.page.getByLabel('Descrizione breve *').fill('un mob ancora cieco')
    await saveForm(s.page)
    assert.equal((await api.byVnum('mobs', 1067)).debuffSkillId, 'curse')
    await s.page.getByText('Ruoli e servizi', { exact: true }).click()
    await s.page.getByLabel('Skill di debuff (opzionale)').fill('')
    await saveForm(s.page)
    assert.equal((await api.byVnum('mobs', 1067)).debuffSkillId ?? null, null)
    await s.page.getByLabel("Torna all'elenco").click()
    await tableRow(s.page, 'un mob ancora cieco').waitFor()
  })

  it('un mob usato da un reset non si elimina (409 tradotto)', async () => {
    s.allow(/409/)
    await tableRow(s.page, 'una guardia').locator('.text-negative').click()
    await confirm(s.page)
    await s.page.getByText(/Impossibile eliminare: il mob è referenziato da 1 comandi di reset/).waitFor()
    await dismissError(s.page)
    assert.ok(await api.byVnum('mobs', 1000))
  })

  it('elimina il mob creato', async () => {
    await tableRow(s.page, 'un goblin rosso').locator('.text-negative').click()
    await confirm(s.page)
    await tableRow(s.page, 'un goblin rosso').waitFor({ state: 'detached' })
    assert.equal(await api.byVnum('mobs', 1050), undefined)
  })

  it('nessun errore di console imprevisto', () => {
    assert.deepEqual(s.errors, [])
  })
})
