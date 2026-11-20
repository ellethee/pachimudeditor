/** Negozi (pachimud): scheda del negoziante nel mob, elenco con ricerca, segnalazione del vecchio `shop_id`. */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import { goto, loginOk, openSession, rawI18nKey, saveForm, type Session } from '../support/browser.ts'

const MOB_VNUM = 1000

describe('negozi', () => {
  let s: Session
  let api: Api

  /** Toglie negozio e `shop_id` dal mob di prova. */
  async function reset(): Promise<void> {
    const mob = await api.byVnum('mobs', MOB_VNUM)
    if (mob) await api.call('PUT', `/api/mobs/${mob.id}`, { shopId: null, extra: { shop: null } })
  }

  before(async () => {
    api = await Api.connect()
    await reset()
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await s.close()
    await reset()
  })

  it('un mob diventa negoziante dalla sua scheda e compare nell\'elenco', async () => {
    await goto(s.page, `/mobs/${MOB_VNUM}`)
    await s.page.getByText('Negozio', { exact: true }).first().click()
    await s.page.getByTestId('shop-toggle').click()
    await s.page.getByTestId('shop-produces').click()
    await s.page.locator('.q-menu .q-item').first().click()
    await s.page.keyboard.press('Escape')
    await s.page.getByTestId('shop-profit-buy').fill('1.5')
    await s.page.getByTestId('shop-close1').fill('20')
    await saveForm(s.page)
    const mob = await api.byVnum('mobs', MOB_VNUM)
    const shop = (await api.call('GET', `/api/mobs/${mob.id}`)).data.extra.shop
    assert.equal(shop.profit_buy, 1.5)
    assert.equal(shop.close1, 20)
    assert.equal(shop.produces.length, 1)
    assert.equal(await rawI18nKey(s.page), null)

    await goto(s.page, '/shops')
    await s.page.getByTestId('shop-row').first().waitFor()
    await s.page.getByTestId('shops-search').fill('zzz-non-esiste')
    await s.page.getByText('Nessun negozio.').waitFor()
    await s.page.getByTestId('shops-search').fill('guardia')
    await s.page.getByTestId('shop-row').first().click()
    await s.page.waitForURL(new RegExp(`/mobs/${MOB_VNUM}$`))
  })

  it('un negozio non valido mostra l\'errore e non salva', async () => {
    await goto(s.page, `/mobs/${MOB_VNUM}`)
    await s.page.getByTestId('shop-profit-buy').fill('-1')
    await s.page.getByTestId('form-save').click()
    await s.page.getByTestId('shop-error').waitFor()
    const mob = await api.byVnum('mobs', MOB_VNUM)
    assert.equal((await api.call('GET', `/api/mobs/${mob.id}`)).data.extra.shop.profit_buy, 1.5)
  })

  it('togliendo il negoziante il mob sparisce dall\'elenco; il vecchio shop_id è segnalato', async () => {
    await goto(s.page, `/mobs/${MOB_VNUM}`)
    await s.page.getByTestId('shop-toggle').click()
    await saveForm(s.page)
    const mob = await api.byVnum('mobs', MOB_VNUM)
    assert.equal((await api.call('GET', `/api/mobs/${mob.id}`)).data.extra.shop, null)
    await api.call('PUT', `/api/mobs/${mob.id}`, { shopId: 'vecchio_negozio' })
    await goto(s.page, '/shops')
    await s.page.getByTestId('shop-legacy-badge').waitFor()
    await s.page.getByTestId('shops-legacy-only').click()
    assert.equal(await s.page.getByTestId('shop-row').count(), 1)
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('nessun errore di console imprevisto', () => {
    assert.deepEqual(s.errors, [])
  })
})
