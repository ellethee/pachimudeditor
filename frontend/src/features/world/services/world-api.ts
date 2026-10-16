import { getUseAlovaInstance } from '@ilpachi/use-alova'
import type { ISearchResults, IWorldOverview, IZoneGraph, IZoneRange, WorldEntityType } from '../types/world'

/**
 * Client HTTP dell'app (@ilpachi/use-alova, cablato da createPachiApp): Authorization, refresh del
 * token, spinner e messaggi di errore sono già gestiti. Risolto a ogni chiamata.
 */
function http() {
  return getUseAlovaInstance()({ url: '/api' }).alova
}

/** Panoramica del mondo: conteggi, riepilogo per zona e warning di qualità. */
export async function getWorldOverview(): Promise<IWorldOverview> {
  return http().Get<IWorldOverview>('/world/overview', { cacheFor: 0 })
}

/** Grafo delle zone (archi = uscite che attraversano il confine di zona). */
export async function getZoneGraph(): Promise<IZoneGraph> {
  return http().Get<IZoneGraph>('/world/zone-graph', { cacheFor: 0 })
}

/**
 * Ricerca globale.
 * @param q - testo cercato (vnum o nome/keywords)
 * @param types - tipi da cercare; vuoto = tutti
 * @param limit - massimo risultati per tipo
 */
export async function searchWorld(q: string, types: WorldEntityType[] = [], limit = 20): Promise<ISearchResults> {
  const params: Record<string, string | number> = { q, limit }
  if (types.length > 0) params.types = types.join(',')
  return http().Get<ISearchResults>('/world/search', { params, cacheFor: 0 })
}

/** Primo range di `span` vnum libero per una nuova zona. */
export async function getNextZoneRange(span = 100): Promise<IZoneRange> {
  return http().Get<IZoneRange>('/world/next-zone-range', { params: { span }, cacheFor: 0 })
}
