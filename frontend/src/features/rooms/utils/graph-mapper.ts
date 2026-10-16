/** Traduce il grafo delle stanze del backend in nodi/archi vue-flow. */

import { MarkerType } from '@vue-flow/core'
import type { Edge, Node } from '@vue-flow/core'
import type { IGraphEdge, IGraphNode } from '../types/rooms'
import { OPPOSITE, type DirectionValue } from './compass'

/** Pixel per unità di griglia del layout calcolato dal server (un'unità = una stanza). */
export const GRID_X = 250
export const GRID_Y = 170

export interface RoomNodeData {
  room: IGraphNode
}

export interface RoomEdgeData {
  edge: IGraphEdge
}

/** Etichetta breve (N, E, S, O, Su, Giù) di una direzione, fornita dal chiamante (i18n). */
export type ShortLabelFn = (direction: DirectionValue) => string

/**
 * Colore e tratteggio di un arco in base alla porta.
 *
 * @param doorFlag - valore del flag porta (1 = chiudibile, 2 = a prova di scasso)
 */
function edgeStyle(doorFlag: number): { stroke: string; dash: string | null } {
  if (doorFlag === 2) return { stroke: '#c62828', dash: '6 4' } // PICKPROOF
  if (doorFlag === 1) return { stroke: '#ef6c00', dash: '6 4' } // CLOSABLE
  return { stroke: '#546e7a', dash: null }
}

/** Id del nodo vue-flow di una stanza. */
export function nodeId(roomId: number): string {
  return String(roomId)
}

/** Id dell'arco vue-flow di un'uscita. */
export function edgeId(exitId: number): string {
  return `e${exitId}`
}

/** Converte un nodo del grafo in nodo vue-flow (posizione = griglia * dimensione cella). */
export function toFlowNode(room: IGraphNode): Node<RoomNodeData> {
  return {
    id: nodeId(room.id),
    type: 'room',
    position: { x: room.x * GRID_X, y: room.y * GRID_Y },
    data: { room },
  }
}

/** Converte un arco del grafo in arco vue-flow, con etichetta direzionale. */
export function toFlowEdge(edge: IGraphEdge, shortLabel: ShortLabelFn): Edge<RoomEdgeData> {
  const direction = edge.direction as DirectionValue
  const opposite = OPPOSITE[direction]
  const { stroke, dash } = edgeStyle(edge.doorFlag)
  const label = edge.twoWay ? `${shortLabel(direction)} ⇄ ${shortLabel(opposite)}` : shortLabel(direction)
  return {
    id: edgeId(edge.id),
    source: nodeId(edge.fromRoomId),
    target: nodeId(edge.toRoomId),
    sourceHandle: `out-${edge.direction}`,
    targetHandle: `in-${opposite}`,
    label,
    labelBgPadding: [6, 3],
    labelBgBorderRadius: 4,
    labelBgStyle: { fill: '#ffffff', fillOpacity: 0.9 },
    labelStyle: { fontSize: '11px', fontWeight: 600, fill: stroke },
    style: { stroke, strokeWidth: 2, ...(dash ? { strokeDasharray: dash } : {}) },
    ...(edge.twoWay ? {} : { markerEnd: { type: MarkerType.ArrowClosed, color: stroke } }),
    data: { edge },
  }
}

/**
 * Converte l'intero grafo; scarta gli archi con estremi fuori dai nodi.
 *
 * @param nodes - nodi del backend
 * @param edges - archi del backend
 * @param shortLabel - etichette brevi delle direzioni
 */
export function graphToFlow(nodes: IGraphNode[], edges: IGraphEdge[], shortLabel: ShortLabelFn) {
  const known = new Set(nodes.map((node) => node.id))
  return {
    nodes: nodes.map(toFlowNode),
    edges: edges
      .filter((edge) => known.has(edge.fromRoomId) && known.has(edge.toRoomId))
      .map((edge) => toFlowEdge(edge, shortLabel)),
  }
}
