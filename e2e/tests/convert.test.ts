/** Conversione tra mondi: BasedMud (scrivibile) -> pachimud con anteprima, conferma e verifica nella pagina Zone. */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import { goto, loginOk, openSession, rawI18nKey, tableRow, type Session } from '../support/browser.ts'

describe('conversione tra mondi', () => {
  let s: Session
  let api: Api

  before(async () => {
    api = await Api.connect()
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await s.close()
  })

  it('la voce e la pagina sono disponibili con piu\' mondi; un arrivo in sola lettura non e\' scegliibile', async () => {
    await goto(s.page, '/convert')
    await s.page.getByTestId('convert-source').waitFor()
    await s.page.getByTestId('convert-source').click()
    await s.page.locator('.q-menu .q-item', { hasText: 'BasedMud (basedmud)' }).first().click()
    await s.page.getByTestId('convert-target').click()
    const items = await s.page.locator('.q-menu .q-item').evaluateAll((els) => els.map((e) => ({ cls: e.className, text: e.textContent ?? '' })))
    const roItems = items.filter((i) => i.text.includes('— sola lettura'))
    assert.ok(roItems.length >= 1 && roItems.every((i) => /disabled/.test(i.cls)))
    await s.page.keyboard.press('Escape')
    assert.match(await s.page.getByTestId('convert-converter').innerText(), /specifiche/)
  })

  it('anteprima: tabelle e perdite, nessuna scrittura', async () => {
    await s.page.getByTestId('convert-zone-search').fill('mud school')
    await tableRow(s.page, 'mud school').locator('.q-checkbox').click()
    await s.page.getByTestId('convert-preview').click()
    await s.page.getByTestId('convert-report').waitFor()
    await s.page.getByTestId('report-zone').getByText('mud school').waitFor()
    await s.page.getByTestId('total-rooms').waitFor()
    await s.page.getByTestId('report-losses').getByTestId('loss-group').first().waitFor()
    assert.equal(await s.page.getByTestId('convert-done').count(), 0)
    assert.equal((await api.call('GET', '/api/zones')).data.items.some((z: { vnum: number }) => z.vnum === 3700), false)
  })

  it('esegue con conferma, poi la zona si vede nel mondo di arrivo', async () => {
    assert.equal(await s.page.getByTestId('convert-run').isDisabled(), true)
    await s.page.getByTestId('convert-confirm').click()
    await s.page.getByTestId('convert-run').click()
    await s.page.getByTestId('convert-done').waitFor()
    assert.equal((await api.call('GET', '/api/zones')).data.items.some((z: { vnum: number }) => z.vnum === 3700), true)
    await Promise.all([s.page.waitForNavigation({ waitUntil: 'load' }), s.page.getByTestId('convert-open-target').click()])
    await s.page.waitForLoadState('networkidle')
    await tableRow(s.page, 'mud school').waitFor()
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('nessun errore di console imprevisto', () => {
    assert.deepEqual(s.errors, [])
  })
})
