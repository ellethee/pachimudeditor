/** Trasferimento zone: export (download zip) e import in anteprima (dry-run, nessuna modifica). */
import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import { credentials } from '../support/stack.ts'
import { BASE_URL, goto, loginOk, openSession, rawI18nKey, type Session } from '../support/browser.ts'

/** Input file di Quasar (q-file). */
const page_files = (s: Session) => s.page.locator('input[type=file]')

describe('trasferimento', () => {
  let s: Session
  let zipPath = ''

  before(async () => {
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await s.close()
  })

  it('esporta una zona: scarica uno zip', async () => {
    await goto(s.page, '/transfer')
    await s.page.waitForLoadState('networkidle')
    await s.page.getByTestId('export-zone').click()
    await s.page.locator('.q-menu .q-item', { hasText: 'Zona Alfa' }).first().click()
    // il download passa da fetch + blob: si legge la risposta (il file scaricato non e' raggiungibile via CDP)
    const [response] = await Promise.all([
      s.page.waitForResponse((r) => /\/api\/transfer\/zones\/\d+\/export/.test(r.url())),
      s.page.getByTestId('export-download').click(),
    ])
    assert.match(response.headers()['content-disposition'] ?? '', /\.zip/)
    assert.equal(response.status(), 200)
    // il corpo della risposta non e' leggibile via CDP (e' consumato dal blob): lo zip da importare si riscarica via API
    const zone = await (await Api.connect()).byVnum('zones', 10)
    const auth = await fetch(`${BASE_URL}/api/auth/token`, {
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ username: credentials.username, password: credentials.password }),
    })
    const token = ((await auth.json()) as { access_token: string }).access_token
    const body = Buffer.from(
      await (await fetch(`${BASE_URL}/api/transfer/zones/${zone.id}/export`, { headers: { authorization: `Bearer ${token}` } })).arrayBuffer(),
    )
    assert.equal(body.subarray(0, 2).toString(), 'PK')
    zipPath = join(mkdtempSync(join(tmpdir(), 'e2e-zip-')), 'zona.zip')
    writeFileSync(zipPath, body)
    assert.equal(await rawI18nKey(s.page), null)
  })

  it('importa lo zip in anteprima: nessuna modifica al DB', async () => {
    const api = await Api.connect()
    const before = (await api.list('rooms')).length
    await page_files(s).setInputFiles(zipPath)
    await s.page.getByTestId('import-preview').click()
    await s.page.getByText('Anteprima', { exact: false }).first().waitFor()
    await s.page.getByText('Stanze', { exact: true }).first().waitFor()
    assert.equal(await s.page.getByTestId('import-done').count(), 0)
    assert.equal((await api.list('rooms')).length, before)
  })

  it('mondo in sola lettura: "Applica" resta disabilitato', async () => {
    await s.page.getByTestId('world-select').click()
    await Promise.all([
      s.page.waitForNavigation({ waitUntil: 'load' }),
      s.page.locator('.q-menu .q-item', { hasText: 'Pachimud (sola lettura)' }).first().click(),
    ])
    await goto(s.page, '/transfer')
    await page_files(s).setInputFiles(zipPath)
    await s.page.getByTestId('import-preview').click()
    await s.page.getByTestId('import-confirm').waitFor()
    await s.page.getByTestId('import-confirm').click()
    assert.equal(await s.page.getByTestId('import-apply').isDisabled(), true)
    assert.equal(await s.page.getByTestId('import-done').count(), 0)
  })

  it('nessun errore di console imprevisto', () => {
    assert.deepEqual(s.errors, [])
  })
})
