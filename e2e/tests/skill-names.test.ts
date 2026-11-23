/**
 * Skill (pachimud): nome italiano (`messages.name`) mostrato in elenco e scheda, `item_types` nel form (un salvataggio che non lo tocca lo
 * lascia com'è) e avvisi sugli incantesimi di una pozione che la skill non ammette.
 */
import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import { Api } from '../support/api.ts'
import { goto, loginOk, openSession, saveForm, type Session } from '../support/browser.ts'

const OBJ_VNUM = 1001
const SKILL = 'pwspell'

describe('skill: nomi italiani e dove possono stare', () => {
  let s: Session
  let api: Api
  let typeValue = { other: 0, potion: 0 }

  /** Toglie la skill di prova e rimette l'oggetto com'era. */
  async function cleanup(): Promise<void> {
    const obj = await api.byVnum('objects', OBJ_VNUM)
    if (obj) await api.call('PUT', `/api/objects/${obj.id}`, { objectType: typeValue.other })
    await api.call('DELETE', `/api/content/skills/${SKILL}`)
  }

  before(async () => {
    api = await Api.connect()
    const types = (await api.get('/api/meta/enums')).data.objectType as { value: number; label: string }[]
    typeValue = {
      other: types.find((t) => t.label.toUpperCase() === 'OTHER')!.value,
      potion: types.find((t) => t.label.toUpperCase() === 'POTION')!.value,
    }
    await cleanup()
    s = await openSession()
    await loginOk(s.page)
  })
  after(async () => {
    await cleanup()
    await s.close()
  })

  it('API: la skill espone nomi e item_types; un tipo non ammesso è rifiutato', async () => {
    const created = await api.post('/api/content/skills', {
      skillId: SKILL,
      kind: 'spell',
      name: 'pw spell',
      itemTypes: ['scroll'],
      advanced: 'messages:\n  name:\n    it: Palla di prova\n    en: test ball\n',
    })
    assert.equal(created.status, 201)
    assert.deepEqual(created.data.itemTypes, ['scroll'])
    assert.deepEqual(created.data.names, { it: 'Palla di prova', en: 'test ball' })
    const bad = await api.call('PUT', `/api/content/skills/${SKILL}`, { itemTypes: ['barile'] })
    assert.equal(bad.status, 422)
  })

  it('UI: nome italiano nell’elenco e nella scheda; salvare senza toccare item_types lo conserva', async () => {
    await goto(s.page, '/content/skills')
    await s.page.getByText('Palla di prova').first().waitFor()
    await s.page.getByTestId('skills-list').getByText(SKILL).first().click()
    await s.page.getByTestId('skill-names').waitFor()
    assert.match(await s.page.getByTestId('skill-names').innerText(), /it: Palla di prova · en: test ball/)
    await s.page.getByLabel('Mana').fill('11')
    await saveForm(s.page)
    const after = (await api.get(`/api/content/skills/${SKILL}`)).data
    assert.equal(after.mana, 11)
    assert.deepEqual(after.itemTypes, ['scroll'])
    assert.deepEqual(after.names, { it: 'Palla di prova', en: 'test ball' })
  })

  it('UI: una pozione con una magia non ammessa mostra l’avviso, sparisce con una pergamena', async () => {
    const obj = await api.byVnum('objects', OBJ_VNUM)
    // il tipo e gli extra del tipo nuovo vanno in due salvataggi: `typeFields.spells` esiste solo per pozioni e pergamene
    assert.equal((await api.call('PUT', `/api/objects/${obj.id}`, { objectType: typeValue.potion })).status, 200)
    const put = await api.call('PUT', `/api/objects/${obj.id}`, { extra: { typeFields: { spells: [SKILL] } } })
    assert.equal(put.status, 200, JSON.stringify(put.body))
    await goto(s.page, `/objects/${OBJ_VNUM}`)
    await s.page.getByTestId('spell-hints').waitFor()
    const text = await s.page.getByTestId('spell-hints').innerText()
    assert.match(text, /Palla di prova|test ball/)
    assert.match(text, /non può stare in un oggetto potion \(ammesso in: scroll\)/)
    const unknown = await api.call('PUT', `/api/objects/${obj.id}`, { extra: { typeFields: { spells: ['non_esiste'] } } })
    assert.equal(unknown.status, 200)
    await goto(s.page, `/objects/${OBJ_VNUM}`)
    await s.page.getByTestId('spell-hints').getByText('«non_esiste» non esiste fra le skill.').waitFor()
  })
})
