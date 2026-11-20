/**
 * Contenuti a strati (skill, social, tabelle, cataloghi) su una copia temporanea delle definizioni: API (creazione, modifica, errori,
 * percorsi vietati) e UI (maschere inline, controllo e ricarica col canale live del finto server pachimud, assenti senza canale).
 */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import { goto, loginOk, openSession, type Session } from '../support/browser.ts'

/** Sceglie un mondo dal selettore nella barra (ricarica la pagina). */
async function pickWorld(s: Session, name: string): Promise<void> {
  await s.page.getByTestId('world-select').click()
  await Promise.all([
    s.page.waitForNavigation({ waitUntil: 'load' }),
    s.page.locator('.q-menu .q-item', { hasText: name }).first().click(),
  ])
}

describe('contenuti a strati', () => {
  let s: Session
  let api: Api

  /** Toglie i dati di prova (anche da un'esecuzione interrotta). */
  async function cleanup(): Promise<void> {
    await api.call('DELETE', '/api/content/skills/pwskill')
    await api.call('DELETE', '/api/content/socials/pwsocial')
    await api.call('DELETE', '/api/content/socials/pwsocialapi')
    await api.call('DELETE', '/api/content/files/locales/it/pw_prova.yaml')
    await api.call('DELETE', '/api/content/files/tables/pw_tabella.yaml')
  }

  before(async () => {
    api = await Api.connect()
    await cleanup()
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await s.close()
    await cleanup()
  })

  it('API: skill (crea, modifica, id doppio, YAML rotto, elimina)', async () => {
    const created = await api.post('/api/content/skills', { skillId: 'pwskill', kind: 'spell', name: 'pw skill', mana: 5, advanced: 'levels:\n  mage: 3\n' })
    assert.equal(created.status, 201)
    assert.equal(created.data.layer, 'user')
    assert.deepEqual(created.data.levels, { mage: 3 })
    assert.equal((await api.post('/api/content/skills', { skillId: 'pwskill' })).status, 409)
    const bad = await api.call('PUT', '/api/content/skills/pwskill', { advanced: 'effects: [\n' })
    assert.equal(bad.status, 422)
    assert.equal(bad.body.detail[0].code, 'content.invalid')
    const saved = await api.call('PUT', '/api/content/skills/pwskill', { mana: 9, violent: true })
    assert.equal(saved.data.mana, 9)
    assert.equal(saved.data.violent, true)
    assert.ok((await api.get('/api/content/skills')).data.some((x: { skillId: string }) => x.skillId === 'pwskill'))
    assert.equal((await api.call('DELETE', '/api/content/skills/pwskill')).status, 204)
    assert.equal((await api.get('/api/content/skills/pwskill')).status, 404)
  })

  it('API: social, file di testo e percorsi vietati', async () => {
    const social = { aliases: ['pw'], position: 'standing', victimMinPosition: 0, hide: false, messages: { it: { no_arg: 'Prova.' } } }
    assert.equal((await api.post('/api/content/socials/pwsocialapi', social)).status, 201)
    assert.deepEqual((await api.get('/api/content/socials')).data.find((x: { name: string }) => x.name === 'pwsocialapi').messages, { it: { no_arg: 'Prova.' } })
    assert.equal((await api.call('PUT', '/api/content/files/locales/it/pw_prova.yaml', { text: 'a: 1\n' })).status, 200)
    assert.equal((await api.call('PUT', '/api/content/files/locales/it/pw_prova.yaml', { text: 'a: [1\n' })).status, 422)
    assert.equal((await api.get('/api/content/files/locales/it/pw_prova.yaml')).data.text, 'a: 1\n')
    assert.equal((await api.call('PUT', '/api/content/files/locales/it/x.txt', { text: 'a' })).status, 422)
    assert.equal((await api.call('PUT', '/api/content/files/tables/socials.yaml', { text: 'a: 1\n' })).status, 422)
    assert.equal((await api.call('PUT', '/api/content/files/nothing/x.yaml', { text: 'a: 1\n' })).status, 422)
  })

  it('UI senza canale live: elenco skill, nessun pulsante di controllo o ricarica', async () => {
    await goto(s.page, '/content/skills')
    await s.page.getByTestId('content-live-off').waitFor()
    assert.equal(await s.page.getByTestId('content-validate').count(), 0)
    assert.equal(await s.page.getByTestId('content-reload').count(), 0)
  })

  it('UI col canale live: crea una skill, controllo, ricarica, elimina', async () => {
    await pickWorld(s, 'Pachimud (live)')
    await goto(s.page, '/content/skills')
    await s.page.getByTestId('content-validate').waitFor()
    await s.page.getByTestId('item-create').click()
    await s.page.getByLabel('Id', { exact: false }).first().fill('pwskill')
    await s.page.getByLabel('Nome', { exact: false }).first().fill('pw skill')
    await s.page.getByLabel('Mana').fill('7')
    await s.page.getByTestId('form-save').first().click()
    await s.page.locator('.q-notification', { hasText: 'Salvato' }).first().waitFor()
    await s.page.getByTestId('content-all-ok').waitFor() // il finto server non ha problemi
    assert.equal((await api.get('/api/content/skills/pwskill')).data.mana, 7)
    await s.page.getByTestId('content-reload').click()
    await s.page.locator('.q-notification', { hasText: 'Il gioco ha riletto' }).first().waitFor()
    await s.page.getByTestId('skill-delete').click()
    await s.page.locator('.q-dialog').last().getByRole('button', { name: 'OK', exact: true }).click()
    await s.page.getByTestId('skill-form').waitFor({ state: 'detached' })
    assert.equal((await api.get('/api/content/skills/pwskill')).status, 404)
  })

  it('UI: social e file di testo (errore con riga, poi salvataggio)', async () => {
    await goto(s.page, '/content/socials')
    await s.page.getByTestId('item-create').click()
    await s.page.getByLabel('Nome', { exact: false }).first().fill('pwsocial')
    await s.page.getByLabel('Senza bersaglio (chi agisce)').first().fill('Salti di gioia.')
    await s.page.getByTestId('form-save').first().click()
    await s.page.locator('.q-notification', { hasText: 'Salvato' }).first().waitFor()
    assert.equal((await api.get('/api/content/socials')).data.find((x: { name: string }) => x.name === 'pwsocial').messages.it.no_arg, 'Salti di gioia.')

    await goto(s.page, '/content/catalogs')
    await s.page.getByTestId('file-create').click()
    await s.page.getByTestId('file-path').fill('it/pw_prova.yaml')
    await s.page.getByTestId('file-text').fill('chiave: [aperta\n')
    await s.page.getByTestId('file-save').click()
    await s.page.getByTestId('file-error').filter({ hasText: 'riga' }).waitFor()
    await s.page.getByTestId('file-text').fill('chiave: valore\n')
    await s.page.getByTestId('file-save').click()
    await s.page.getByTestId('file-row').filter({ hasText: 'it/pw_prova.yaml' }).waitFor()
    assert.equal((await api.get('/api/content/files/locales/it/pw_prova.yaml')).data.text, 'chiave: valore\n')
    await goto(s.page, '/content/tables')
    await s.page.getByTestId('files-list').waitFor()
  })
})
