/** File grezzi delle zone: API (etag, YAML rotto, schema) e UI (editor, errori con riga e colonna, link dal dettaglio zona). */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import { goto, loginOk, openSession, type Session } from '../support/browser.ts'

const PATH = 'ZonaAlfa/mobs.yaml'
const URL = `/api/content/zonefiles/${PATH}`

describe('file grezzi delle zone', () => {
  let s: Session
  let api: Api
  let original = ''

  /** Rimette il testo originale del file. */
  async function restore(): Promise<void> {
    if (original) await api.call('PUT', URL, { text: original })
  }
  /** Il testo nell'editor. */
  const editorText = () => s.page.getByTestId('zonefile-text').locator('.cm-content')

  before(async () => {
    api = await Api.connect()
    original = (await api.get(URL)).data.text
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await s.close()
    await restore()
  })

  it('UI: apre un file mobs, il testo compare nell\'editor', async () => {
    await goto(s.page, '/zones/files?zone=ZonaAlfa')
    await s.page.getByTestId('zonefile-row').filter({ hasText: 'mobs.yaml' }).click()
    await s.page.getByTestId('zonefile-editor').waitFor()
    assert.match(await editorText().innerText(), /guardia/)
    assert.equal(await s.page.getByTestId('zonefile-row').filter({ hasText: 'ZonaVuota' }).count(), 0) // filtro per zona
  })

  it('UI: la prima modifica dopo l\'apertura viene sottolineata dallo schema', async () => {
    const text = (await api.get(URL)).data.text
    await editorText().fill(text.replace('level: 1', 'level: molto'))
    await s.page.locator('.cm-lintRange').first().waitFor({ timeout: 8000 })
    await editorText().fill(text) // ripristina: nessuna modifica pendente
  })

  it('UI: un file lungo scorre nell\'editor, la pagina non sfora', async () => {
    await editorText().fill('mobs:\n' + '# riga\n'.repeat(300))
    const m = await s.page.evaluate(() => {
      const sc = document.querySelector('.cm-scroller') as HTMLElement
      const save = document.querySelector('[data-testid=zonefile-save]') as HTMLElement
      return { doc: document.documentElement.scrollHeight, win: innerHeight, scrolls: sc.scrollHeight > sc.clientHeight, saveBottom: save.getBoundingClientRect().bottom }
    })
    assert.ok(m.doc <= m.win + 1 && m.scrolls && m.saveBottom <= m.win, JSON.stringify(m))
    await editorText().fill(original)
  })

  it('UI: modifica valida e salva', async () => {
    await editorText().fill(original.replace('un ratto', 'un topo'))
    await s.page.getByTestId('zonefile-dirty').waitFor()
    await s.page.getByTestId('zonefile-save').click()
    await s.page.locator('.q-notification', { hasText: 'File salvato' }).first().waitFor()
    assert.match((await api.get(URL)).data.text, /un topo/)
    await s.page.getByTestId('zonefile-dirty').waitFor({ state: 'detached' })
  })

  it('UI: YAML rotto, errore con riga e colonna, file invariato', async () => {
    const before = (await api.get(URL)).data.text
    await editorText().fill('mobs: [aperta\n')
    await s.page.getByTestId('zonefile-save').click()
    await s.page.getByTestId('code-editor-error').filter({ hasText: /riga \d+, colonna \d+/ }).waitFor()
    assert.equal((await api.get(URL)).data.text, before)
  })

  it('UI: violazione di schema, errore con riga e file invariato', async () => {
    const before = (await api.get(URL)).data.text
    await editorText().fill(before.replace('level: 1', 'level: molto'))
    await s.page.getByTestId('zonefile-save').click()
    await s.page.getByTestId('code-editor-error').filter({ hasText: /riga \d+/ }).waitFor()
    await s.page.getByTestId('zonefile-issues').waitFor()
    assert.equal((await api.get(URL)).data.text, before)
  })

  it('UI: file cambiato altrove, avviso e ricarica dal disco', async () => {
    await goto(s.page, '/zones/files')
    await s.page.getByTestId('zonefile-row').filter({ hasText: 'ZonaAlfa' }).filter({ hasText: 'mobs.yaml' }).click()
    await s.page.getByTestId('zonefile-editor').waitFor()
    const disk = (await api.get(URL)).data.text
    await api.call('PUT', URL, { text: disk.replace('un topo', 'un gatto') })
    await editorText().fill(disk.replace('guardia', 'soldato'))
    await s.page.getByTestId('zonefile-save').click()
    await s.page.getByTestId('zonefile-changed').waitFor()
    assert.match((await api.get(URL)).data.text, /un gatto/)
    await s.page.getByTestId('zonefile-reload').click()
    await s.page.getByTestId('zonefile-changed').waitFor({ state: 'detached' })
    assert.match(await editorText().innerText(), /un gatto/)
  })

  it('UI: link «File grezzi» dal dettaglio della zona', async () => {
    const zone = await api.byVnum('zones', 10)
    await goto(s.page, `/zones/${zone.id}`)
    await s.page.getByTestId('zone-raw-files').click()
    await s.page.getByTestId('zonefile-row').first().waitFor()
    assert.match(s.page.url(), /zone=ZonaAlfa/)
    assert.equal(await s.page.getByTestId('zonefile-row').filter({ hasText: 'ZonaVuota' }).count(), 0)
  })
})
