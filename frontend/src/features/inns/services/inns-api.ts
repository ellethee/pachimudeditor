import { getUseAlovaInstance } from '@ilpachi/use-alova'
import type { IInnItem } from '../types/inns'

/** Client HTTP dell'app, risolto a ogni chiamata. */
function http(base: string) {
  return getUseAlovaInstance()({ url: base }).alova
}

/** I mob `receptionist` con le stanze dove compaiono (`GET /api/content/inns`). */
export async function listInns(): Promise<IInnItem[]> {
  return http('/api/content').Get<IInnItem[]>('/inns', { meta: { autoError: false }, cacheFor: 0 })
}

/** Crea un locandiere da template nella zona (`POST /api/mobs`, `extra.receptionist`); restituisce il vnum. */
export async function createInnkeeper(zoneId: number, vnum: number, name: string): Promise<number> {
  const created = await http('/api/mobs').Post<{ vnum: number }>(
    '',
    {
      vnum,
      zoneId,
      keywords: `receptionist locandiere ${name}`.trim(),
      shortDescription: name,
      longDescription: `${name} e' qui a prendersi cura dei viandanti.`,
      detailedDescription: 'Seria e compassata, non commette errori.',
      level: 23,
      thac0: 0,
      armorClass: -1,
      hpDiceCount: 90,
      hpDieSize: 5,
      hpBonus: 10,
      damageDiceCount: 1,
      damageDieSize: 8,
      damageBonus: 2,
      gold: 2000,
      alignment: 900,
      flags: ['SENTINEL'],
      extra: { receptionist: true },
    },
    { meta: { autoError: false } },
  )
  return created.vnum
}
