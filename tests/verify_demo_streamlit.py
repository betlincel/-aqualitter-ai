"""Run the full Streamlit scenario twice and inspect the actual Folium polylines."""

import hashlib
import json
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import folium
from folium.plugins import PolyLineTextPath
from streamlit.testing.v1 import AppTest
from coastline import load_natural_earth_zip
from ui_shell import PAGES
from marine_routes import (
    DEMO_SCENARIO_NODES, DEMO_VESSEL_NODES, KM_PER_NAUTICAL_MILE,
    build_land_checked_links, compare_visit_orders, haversine_km,
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def main():
    source = ROOT / "data" / "ne_10m_land.zip"
    records = ROOT / "data" / "confirmed_observations.json"
    before = (digest(source), digest(records))
    selected = list(DEMO_SCENARIO_NODES)
    visits = tuple(f"scenario-demo-{letter}" for letter in "fbdace")
    order_key = "marine_visit_order_" + hashlib.sha1(
        ("Senaryo|" + "|".join(selected)).encode()
    ).hexdigest()[:10]
    at = AppTest.from_file(str(ROOT / "app.py"))
    at.session_state['active_page'] = PAGES[3]
    at.session_state['marine_route_stops_scenario'] = selected
    at.session_state['marine_route_start'] = 'vessel-west'
    at.session_state['marine_route_return'] = 'vessel-west'
    at.session_state[order_key] = visits

    polylines = []
    original_init = folium.PolyLine.__init__
    fit_bounds, arrows = [], []
    original_fit = folium.map.FitBounds.__init__
    original_arrow = PolyLineTextPath.__init__

    def capture(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        polylines.append(self.locations)

    def capture_bounds(self, bounds, *args, **kwargs):
        original_fit(self, bounds, *args, **kwargs)
        fit_bounds.append((bounds, self.options))

    def capture_arrows(self, *args, **kwargs):
        original_arrow(self, *args, **kwargs)
        arrows.append(self.options)

    folium.PolyLine.__init__ = capture
    folium.map.FitBounds.__init__ = capture_bounds
    PolyLineTextPath.__init__ = capture_arrows
    times, generated = [], []
    try:
        for _ in range(2):
            polylines.clear()
            fit_bounds.clear()
            arrows.clear()
            started = perf_counter()
            at.run(timeout=90)
            times.append(perf_counter() - started)
            assert not at.exception, [str(x) for x in at.exception]
            assert not at.error, [x.value for x in at.error]
            assert at.status[0].state == 'complete'
            assert len(polylines) == 14, len(polylines)
            assert len(fit_bounds) == 2 and fit_bounds[0] == fit_bounds[1], fit_bounds
            bounds = fit_bounds[0][0]
            for line in polylines:
                for latitude, longitude in line:
                    assert bounds[0][0] <= latitude <= bounds[1][0]
                    assert bounds[0][1] <= longitude <= bounds[1][1]
            assert len(arrows) == 14 and all(not x['repeat'] and x['center'] for x in arrows)
            generated.append([
                sum(haversine_km(a, b) for line in polylines[offset:offset + 7]
                    for a, b in zip(line, line[1:]))
                for offset in (0, 7)
            ])
    finally:
        folium.PolyLine.__init__ = original_init
        folium.map.FitBounds.__init__ = original_fit
        PolyLineTextPath.__init__ = original_arrow

    mask = load_natural_earth_zip(source)
    links, unavailable = build_land_checked_links(
        {**DEMO_VESSEL_NODES, **DEMO_SCENARIO_NODES}, mask
    )
    expected = compare_visit_orders('vessel-west', 'vessel-west', list(visits), links, unavailable)
    for current, recommended in generated:
        assert abs(current - expected['current_km']) < 1e-9
        assert abs(recommended - expected['recommended_km']) < 1e-9
    assert before == (digest(source), digest(records)), 'User records or land ZIP changed'
    print(json.dumps({
        'first_full_streamlit_s': times[0], 'repeat_full_streamlit_s': times[1],
        'current_order': expected['current_order'], 'recommended_order': expected['recommended_order'],
        'current_km': expected['current_km'], 'recommended_km': expected['recommended_km'],
        'current_nm': expected['current_km'] / KM_PER_NAUTICAL_MILE,
        'recommended_nm': expected['recommended_km'] / KM_PER_NAUTICAL_MILE,
        'difference_km': expected['difference_km'],
        'actual_folium_leg_counts': [7, 7], 'status': at.status[0].state,
        'same_map_bounds': True, 'sparse_direction_arrows': True,
        'records_and_zip_unchanged': True, 'zip_sha256': before[0],
    }, ensure_ascii=True))


if __name__ == '__main__':
    main()
