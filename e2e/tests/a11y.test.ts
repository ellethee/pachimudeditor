/** Accessibilita' e layout stretto: pulsanti icona con nome, barra e tabelle di conversione entro lo schermo a 375 px. */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { goto, loginOk, openSession, type Session } from '../support/browser.ts'

describe('accessibilita e responsive', () => {
  let s: Session

  before(async () => {
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await s.close()
  })

  it('nessun pulsante visibile senza nome accessibile', async () => {
    for (const path of ['/zones', '/rooms', '/mobs', '/objects', '/instances', '/players', '/content/races', '/content/classes', '/world/graph', '/rooms/map']) {
      await goto(s.page, path)
      await s.page.waitForTimeout(1200)
      const unnamed = await s.page.evaluate(() =>
        [...document.querySelectorAll('button,[role=button]')]
          .filter((e) => e.getBoundingClientRect().width > 0 && !(e.getAttribute('aria-label') || e.getAttribute('title') || e.textContent?.trim()))
          .map((e) => String(e.className).slice(0, 60)),
      )
      assert.deepEqual(unnamed, [], path)
    }
  })

  it('a 375 px barra e tabelle della conversione restano nello schermo', async () => {
    await s.page.setViewportSize({ width: 375, height: 800 })
    await goto(s.page, '/convert')
    await s.page.getByTestId('convert-zones').locator('tbody tr').first().locator('.q-checkbox').click()
    await s.page.getByTestId('convert-preview').click()
    await s.page.getByTestId('convert-report').waitFor()
    const overflow = await s.page.evaluate(() => ({
      selectRight: document.querySelector('[data-testid=world-selector]')?.getBoundingClientRect().right ?? 0,
      avatarRight: [...document.querySelectorAll('.pachi-app-bar button')].pop()?.getBoundingClientRect().right ?? 0,
      tables: [...document.querySelectorAll('.q-table__container')].map((e) => e.getBoundingClientRect().right),
      width: innerWidth,
    }))
    assert.ok(overflow.avatarRight <= overflow.width, 'barra oltre lo schermo')
    assert.ok(overflow.selectRight <= overflow.width, 'selettore oltre lo schermo')
    for (const right of overflow.tables) assert.ok(right <= overflow.width, `tabella oltre lo schermo (${right})`)
  })
})
