"""Small, explicitly scenario-only maritime route graph for the Trabzon demo."""

from __future__ import annotations

from collections import Counter
from itertools import permutations
from math import asin, cos, radians, sin, sqrt


# Fixed scenario vessel positions and six illustrative offshore visit points.
# Arbitrary real observation coordinates are deliberately not snapped into this graph.
DEMO_VESSEL_NODES = {
    "vessel-west": {
        "label": "Trabzon aciklari - bati (senaryo tekne noktasi)",
        "latitude": 41.0450,
        "longitude": 39.6900,
    },
    "vessel-east": {
        "label": "Trabzon aciklari - dogu (senaryo tekne noktasi)",
        "latitude": 41.0450,
        "longitude": 39.8200,
    },
}

DEMO_SCENARIO_NODES = {
    "scenario-demo-a": {
        "label": "Senaryo A",
        "latitude": 41.0350,
        "longitude": 39.7050,
    },
    "scenario-demo-b": {
        "label": "Senaryo B",
        "latitude": 41.0550,
        "longitude": 39.7300,
    },
    "scenario-demo-c": {
        "label": "Senaryo C",
        "latitude": 41.0400,
        "longitude": 39.7550,
    },
    "scenario-demo-d": {
        "label": "Senaryo D",
        "latitude": 41.0650,
        "longitude": 39.7800,
    },
    "scenario-demo-e": {
        "label": "Senaryo E",
        "latitude": 41.0380,
        "longitude": 39.8050,
    },
    "scenario-demo-f": {
        "label": "Senaryo F",
        "latitude": 41.0600,
        "longitude": 39.8350,
    },
}

DEMO_CORRIDOR_LATITUDE = 41.0450
EARTH_RADIUS_KM = 6371.0088
KM_PER_NAUTICAL_MILE = 1.852


class RouteNotAvailable(ValueError):
    """Raised when a requested point has no prepared demo maritime connection."""


def repeated_edge_passes(legs: list[dict]) -> list[tuple[int, int]]:
    """Return (total uses, this pass number) for each undirected route leg."""
    totals = Counter(frozenset((leg["from"], leg["to"])) for leg in legs)
    used: Counter = Counter()
    result = []
    for leg in legs:
        key = frozenset((leg["from"], leg["to"]))
        used[key] += 1
        result.append((totals[key], used[key]))
    return result


def haversine_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    """Great-circle distance between two (latitude, longitude) points."""
    lat1, lon1 = map(radians, first)
    lat2, lon2 = map(radians, second)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    value = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(min(1.0, value)))


def _build_demo_link(first_id: str, second_id: str) -> list[tuple[float, float]]:
    """Build a fixed-corridor demo link between known nodes, never arbitrary points."""
    nodes = {**DEMO_VESSEL_NODES, **DEMO_SCENARIO_NODES}
    if first_id not in nodes or second_id not in nodes:
        raise RouteNotAvailable("Bu nokta Trabzon senaryo deniz bağlantı ağına bağlı değil.")
    return build_corridor_link(nodes[first_id], nodes[second_id])


def build_corridor_link(
    first: dict,
    second: dict,
    corridor_latitude: float = DEMO_CORRIDOR_LATITUDE,
) -> list[tuple[float, float]]:
    """Create a candidate polyline; callers must validate it against a land mask."""
    points = [
        (first["latitude"], first["longitude"]),
        (corridor_latitude, first["longitude"]),
        (corridor_latitude, second["longitude"]),
        (second["latitude"], second["longitude"]),
    ]
    compact: list[tuple[float, float]] = []
    for point in points:
        if not compact or point != compact[-1]:
            compact.append(point)
    return compact


def build_land_checked_links(
    nodes: dict[str, dict],
    land_mask,
    corridor_latitude: float = DEMO_CORRIDOR_LATITUDE,
) -> tuple[dict[tuple[str, str], list[tuple[float, float]]], dict[str, str]]:
    """Build only legs whose full corridor polyline clears the supplied land mask."""
    links: dict[tuple[str, str], list[tuple[float, float]]] = {}
    unavailable: dict[str, str] = {}
    for node_id, node in nodes.items():
        reason = land_mask.validate_path([(node["latitude"], node["longitude"])])
        if reason:
            unavailable[node_id] = reason

    for index, first_id in enumerate(nodes):
        for second_id in list(nodes)[index + 1 :]:
            first, second = nodes[first_id], nodes[second_id]
            candidate = build_corridor_link(first, second, corridor_latitude)
            reason = land_mask.validate_path(candidate)
            if reason:
                unavailable[f"{first_id} → {second_id}"] = reason
                unavailable[f"{second_id} → {first_id}"] = reason
                continue
            links[(first_id, second_id)] = candidate
            links[(second_id, first_id)] = list(reversed(candidate))
    return links, unavailable


# Only these fixed endpoint pairs are connected in this prototype. The polyline
# is an illustrative offshore corridor, not a charted or navigational route.
DEMO_LINKS: dict[frozenset[str], list[tuple[float, float]]] = {
    frozenset((first, second)): _build_demo_link(first, second)
    for index, first in enumerate((*DEMO_VESSEL_NODES, *DEMO_SCENARIO_NODES))
    for second in (*DEMO_VESSEL_NODES, *DEMO_SCENARIO_NODES)[index + 1 :]
}


def get_demo_link(first_id: str, second_id: str) -> list[tuple[float, float]]:
    """Return a configured link in requested direction; do not synthesize unknown links."""
    if first_id == second_id:
        nodes = {**DEMO_VESSEL_NODES, **DEMO_SCENARIO_NODES}
        if first_id not in nodes:
            raise RouteNotAvailable("Bu nokta Trabzon senaryo deniz bağlantı ağına bağlı değil.")
        node = nodes[first_id]
        return [(node["latitude"], node["longitude"])]
    key = frozenset((first_id, second_id))
    if key not in DEMO_LINKS:
        raise RouteNotAvailable(
            "Seçilen konumlar için hazırlanmış deniz bağlantısı yok; konum taşınmadı."
        )
    points = DEMO_LINKS[key]
    if points[0] == (
        {**DEMO_VESSEL_NODES, **DEMO_SCENARIO_NODES}[first_id]["latitude"],
        {**DEMO_VESSEL_NODES, **DEMO_SCENARIO_NODES}[first_id]["longitude"],
    ):
        return points.copy()
    return list(reversed(points))


def route_distance_km(
    node_order: list[str],
    links: dict[tuple[str, str], list[tuple[float, float]]] | None = None,
    unavailable: dict[str, str] | None = None,
) -> tuple[float, list[dict]]:
    """Measure a closed/open route along the prepared polylines, not land chords."""
    total_km = 0.0
    legs: list[dict] = []
    for first_id, second_id in zip(node_order, node_order[1:]):
        if links is None:
            points = get_demo_link(first_id, second_id)
        else:
            points = links.get((first_id, second_id))
            if points is None:
                reason = (unavailable or {}).get(f"{first_id} → {second_id}")
                raise RouteNotAvailable(
                    f"{first_id} ile {second_id} arasında doğrulanmış deniz bağlantısı yok"
                    + (f": {reason}" if reason else ".")
                )
        leg_km = sum(haversine_km(a, b) for a, b in zip(points, points[1:]))
        total_km += leg_km
        legs.append(
            {
                "from": first_id,
                "to": second_id,
                "coordinates": points,
                "distance_km": leg_km,
            }
        )
    return total_km, legs


def compare_visit_orders(
    start_id: str,
    return_id: str,
    visit_order: list[str],
    links: dict[tuple[str, str], list[tuple[float, float]]] | None = None,
    unavailable: dict[str, str] | None = None,
) -> dict:
    """Compare current visit order with the shortest order in the prepared graph."""
    if len(visit_order) > 6:
        raise RouteNotAvailable("Bu prototip en fazla 6 ziyaret noktasını sıralar.")
    if len(visit_order) != len(set(visit_order)):
        raise RouteNotAvailable("Aynı gözlem ziyaret listesine birden fazla eklenemez.")

    current_order = [start_id, *visit_order, return_id]
    current_km, current_legs = route_distance_km(current_order, links, unavailable)

    if not visit_order:
        return {
            "current_order": [],
            "recommended_order": [],
            "current_nodes": current_order,
            "recommended_nodes": current_order.copy(),
            "current_legs": current_legs,
            "recommended_legs": current_legs.copy(),
            "current_km": current_km,
            "recommended_km": current_km,
            "difference_km": 0.0,
            "improvement_km": 0.0,
            "improved": False,
        }

    best_order: tuple[str, ...] | None = None
    best_km = float("inf")
    best_legs: list[dict] = []
    for candidate in permutations(visit_order):
        candidate_order = [start_id, *candidate, return_id]
        try:
            candidate_km, candidate_legs = route_distance_km(
                candidate_order, links, unavailable
            )
        except RouteNotAvailable:
            continue
        if candidate_km < best_km:
            best_order = candidate
            best_km = candidate_km
            best_legs = candidate_legs

    if best_order is None:
        raise RouteNotAvailable("Ziyaret sıralarının hiçbiri doğrulanmış bağlantı ağında değil.")
    optimized_visits = list(best_order)
    difference_km = current_km - best_km
    return {
        "current_order": visit_order.copy(),
        "recommended_order": optimized_visits,
        "current_nodes": current_order,
        "recommended_nodes": [start_id, *optimized_visits, return_id],
        "current_legs": current_legs,
        "recommended_legs": best_legs,
        "current_km": current_km,
        "recommended_km": best_km,
        "difference_km": difference_km,
        "improvement_km": max(0.0, difference_km),
        "improved": difference_km > 1e-9,
    }
