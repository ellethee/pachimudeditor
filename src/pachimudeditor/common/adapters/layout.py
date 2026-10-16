"""Layout a bussola di un grafo di stanze: funzioni pure, nessun database.

Le stanze vengono posizionate su una griglia seguendo le loro uscite (N=(0,-1) S=(0,1)
E=(1,0) O=(-1,0) e, come offset obliqui per non sovrapporsi alla griglia orizzontale,
Su=(0.6,-0.6) Giù=(-0.6,0.6)). Ogni componente connessa viene disposta con una visita in
ampiezza a partire dalla stanza col vnum più basso; una stanza che finirebbe su una cella
occupata viene spostata a spirale sulla cella libera più vicina; le componenti vengono
messe una accanto all'altra, da sinistra a destra, in ordine di vnum più basso.
"""

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

from pachimudeditor.common.enums import Direction

DIRECTION_VECTORS: dict[Direction, tuple[float, float]] = {
    Direction.NORTH: (0.0, -1.0),
    Direction.SOUTH: (0.0, 1.0),
    Direction.EAST: (1.0, 0.0),
    Direction.WEST: (-1.0, 0.0),
    Direction.UP: (0.6, -0.6),
    Direction.DOWN: (-0.6, 0.6),
}
"""Offset di griglia di un'uscita per ciascuna direzione (y cresce verso il basso, come sullo schermo)."""

COMPONENT_GAP = 2.0
"""Colonne di griglia vuote lasciate tra due componenti affiancate."""

_MAX_SPIRAL_RADIUS = 200


@dataclass(frozen=True)
class LayoutNode:
    """Una stanza da posizionare: id e vnum (il vnum decide l'inizio di ogni componente)."""

    id: int
    vnum: int


@dataclass(frozen=True)
class LayoutEdge:
    """Un'uscita `from_id --direction--> to_id`. Il layout la tratta come non orientata."""

    from_id: int
    to_id: int
    direction: Direction


def _key(x: float, y: float) -> tuple[float, float]:
    """Chiave di occupazione di una cella di griglia, priva del rumore dei float."""
    return (round(x, 3), round(y, 3))


def _spiral_offsets(radius: int) -> list[tuple[int, int]]:
    """Offset interi a distanza di Chebyshev `radius`, dal più vicino (euclideo), a parità per y poi x."""
    ring = [(dx, dy) for dx in range(-radius, radius + 1) for dy in range(-radius, radius + 1) if max(abs(dx), abs(dy)) == radius]
    return sorted(ring, key=lambda o: (o[0] ** 2 + o[1] ** 2, o[1], o[0]))


def _nearest_free(x: float, y: float, occupied: set[tuple[float, float]]) -> tuple[float, float]:
    """`(x, y)` stessa se libera, altrimenti la cella libera più vicina trovata espandendo anelli."""
    if _key(x, y) not in occupied:
        return x, y
    for radius in range(1, _MAX_SPIRAL_RADIUS):
        for dx, dy in _spiral_offsets(radius):
            candidate = (x + dx, y + dy)
            if _key(*candidate) not in occupied:
                return candidate
    return x, y  # irraggiungibile in pratica: la spirale dovrebbe essere del tutto piena


def compute_layout(nodes: Sequence[LayoutNode], edges: Sequence[LayoutEdge]) -> dict[int, tuple[float, float]]:
    """Restituisce `{node_id: (x, y)}` in unità di griglia per ogni nodo."""
    known = {node.id: node for node in nodes}
    neighbours: dict[int, list[tuple[int, tuple[float, float]]]] = {node.id: [] for node in nodes}
    for edge in edges:
        vector = DIRECTION_VECTORS.get(edge.direction)
        if vector is None or edge.from_id not in known or edge.to_id not in known or edge.from_id == edge.to_id:
            continue
        neighbours[edge.from_id].append((edge.to_id, vector))
        neighbours[edge.to_id].append((edge.from_id, (-vector[0], -vector[1])))

    positions: dict[int, tuple[float, float]] = {}
    next_left = 0.0
    for start in sorted(nodes, key=lambda n: (n.vnum, n.id)):
        if start.id in positions:
            continue
        component: dict[int, tuple[float, float]] = {}
        occupied: set[tuple[float, float]] = set()
        component[start.id] = (0.0, 0.0)
        occupied.add(_key(0.0, 0.0))
        queue: deque[int] = deque([start.id])
        while queue:
            current = queue.popleft()
            cx, cy = component[current]
            for other_id, (dx, dy) in sorted(neighbours[current], key=lambda n: (known[n[0]].vnum, n[0])):
                if other_id in component or other_id in positions:
                    continue
                placed = _nearest_free(cx + dx, cy + dy, occupied)
                component[other_id] = placed
                occupied.add(_key(*placed))
                queue.append(other_id)

        shift = next_left - min(x for x, _ in component.values())
        for node_id, (x, y) in component.items():
            positions[node_id] = (round(x + shift, 3), round(y, 3))
        next_left = max(x for x, _ in positions.values()) + COMPONENT_GAP
    return positions
