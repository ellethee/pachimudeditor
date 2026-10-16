/** Pagina "nessun mondo": backend senza mondi -> redirect a /no-worlds con le istruzioni; con un mondo non compare. */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { BASE_URL, loginAt, openSession, rawI18nKey, type Session } from '../support/browser.ts'
import { startStack, type Stack } from '../support/stack.ts'

/** Porta dedicata (diversa dallo stack principale e dalle porte dell'utente). */
const PORT = Number(process.env.E2E_NOWORLDS_PORT ?? 8125)

describe('nessun mondo configurato', () => {
  let empty: Stack
  let s: Session
  before(async () => {
    empty = await startStack(PORT, { noWorlds: true })
    s = await openSession()
  })
  after(async () => {
    await s?.close()
    await empty?.stop()
  })

  it('senza mondi il login porta a /no-worlds con le istruzioni di configurazione', async () => {
    s.allow(/404/) // le chiamate ai mondi rispondono world.none_configured
    await loginAt(s.page, empty.baseUrl)
    await s.page.waitForURL(/\/no-worlds$/)
    const page = s.page.getByTestId('no-worlds')
    await page.waitFor()
    const text = await page.innerText()
    assert.match(text, /webeditor_worlds/)
    assert.match(text, /kind: basedmud/)
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('con un mondo configurato (stack principale) la pagina non compare', async () => {
    const session = await openSession()
    try {
      await loginAt(session.page, BASE_URL)
      await session.page.getByText('Overview').first().waitFor()
      assert.doesNotMatch(session.page.url(), /no-worlds/)
      assert.equal(await session.page.getByTestId('no-worlds').count(), 0)
      await session.page.goto(`${BASE_URL}/no-worlds`)
      await session.page.getByTestId('world-select').waitFor()
    } finally {
      await session.close()
    }
  })
})
