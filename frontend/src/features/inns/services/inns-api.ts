import { getUseAlovaInstance } from '@ilpachi/use-alova'
import { getResetCommands, replaceResetCommands } from '../../zones/services/zones-api'
import { CommandType } from '../../zones/utils/reset-commands'
import type { IInnItem, IInnkeeperCreated } from '../types/inns'

/** Client HTTP dell'app, risolto a ogni chiamata. */
function http(base: string) {
  return getUseAlovaInstance()({ url: base }).alova
}

/** I mob `receptionist` con le stanze dove compaiono (`GET /api/content/inns`). */
export async function listInns(): Promise<IInnItem[]> {
  return http('/api/content').Get<IInnItem[]>('/inns', { meta: { autoError: false }, cacheFor: 0 })
}

/**
 * Crea un locandiere da template nella zona (`POST /api/mobs`, `extra.receptionist`). Con `room` aggiunge in coda allo script di reset
 * della zona della stanza un `M` che lo carica (se il mob e la stanza sono di zone diverse vale la zona della stanza).
 * Se il reset fallisce il mob resta creato e `spawnError` dice perché.
 */
export async function createInnkeeper(
  zoneId: number,
  vnum: number,
  name: string,
  room: { vnum: number; zoneId: number } | null,
): Promise<IInnkeeperCreated> {
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
  if (!room) return { vnum: created.vnum, spawnedInZoneId: null, spawnError: null }
  try {
    const script = await getResetCommands(room.zoneId)
    const keep = script.map(({ id: _id, zoneId: _zone, orderIndex: _order, extra: _extra, ...step }) => step)
    await replaceResetCommands(room.zoneId, [
      ...keep,
      { commandType: CommandType.LOAD_MOB, ifFlag: false, arg1: created.vnum, arg2: 1, arg3: room.vnum, arg4: 1, argStr: null },
    ])
    return { vnum: created.vnum, spawnedInZoneId: room.zoneId, spawnError: null }
  } catch (e) {
    return { vnum: created.vnum, spawnedInZoneId: null, spawnError: e instanceof Error ? e.message : String(e) }
  }
}
