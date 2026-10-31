"""Check live-script estimate refresh/removal with the real local land mask."""

import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest
from fuel_estimates import compare_fuel_co2
from marine_routes import DEMO_SCENARIO_NODES
from ui_shell import PAGES


def values(at):
    return {x.label: x.value for x in at.metric if 'tahmini' in x.label}


def main():
    records = ROOT / 'data' / 'confirmed_observations.json'
    before = hashlib.sha256(records.read_bytes()).hexdigest() if records.is_file() else None
    selected = list(DEMO_SCENARIO_NODES)
    key = 'marine_visit_order_' + hashlib.sha1(('Senaryo|' + '|'.join(selected)).encode()).hexdigest()[:10]
    at = AppTest.from_file(str(ROOT / 'app.py'))
    at.session_state['active_page'] = PAGES[3]
    at.session_state['marine_route_stops_scenario'] = selected
    at.session_state['marine_route_start'] = 'vessel-west'
    at.session_state['marine_route_return'] = 'vessel-west'
    at.session_state[key] = tuple(f'scenario-demo-{x}' for x in 'fbdace')
    at.run(timeout=90)
    assert not at.exception and not at.error
    at.radio(key='active_page').set_value(PAGES[4]); at.run(timeout=90)
    assert at.number_input(key='marine_fuel_consumption').value is None
    assert not values(at)

    for rate in (2.0, 3.0):
        at.number_input(key='marine_fuel_consumption').set_value(rate)
        at.run(timeout=90)
        assert not at.exception and not at.error
        expected = compare_fuel_co2(64.37911378355338, 39.22031396657271, rate)
        displayed = values(at)
        assert len(displayed) == 6, displayed
        assert displayed['Mevcut tahmini yakıt'] == f"{expected['current']['fuel_l']:.2f} L"
        assert displayed['Önerilen tahmini egzoz CO₂'] == f"{expected['recommended']['co2_kg']:.2f} kg CO₂"
        assert displayed['Fark tahmini yakıt'] == f"{expected['difference']['fuel_l']:+.2f} L"
    at.radio(key='active_page').set_value(PAGES[3]); at.run(timeout=90)
    at.selectbox(key=key).set_value(tuple(f'scenario-demo-{x}' for x in 'fedcba'))
    at.run(timeout=90)
    at.radio(key='active_page').set_value(PAGES[4]); at.run(timeout=90)
    assert values(at)['Fark tahmini yakıt'] == '+0.00 L'
    assert values(at)['Fark tahmini egzoz CO₂'] == '+0.00 kg CO₂'

    at.number_input(key='marine_fuel_consumption').set_value(0.0)
    at.run(timeout=90)
    assert not at.exception and at.error
    assert not values(at), 'Invalid consumption left stale results'
    at.number_input(key='marine_fuel_consumption').set_value(None)
    at.run(timeout=90)
    assert not at.exception and not at.error and not values(at)
    at.number_input(key='marine_fuel_consumption').set_value(2.0)
    at.run(timeout=90)
    assert len(values(at)) == 6

    # Invalid visit exists only in this isolated process; never write an observation.
    invalid = {**DEMO_SCENARIO_NODES['scenario-demo-a'], 'latitude': 41.008, 'longitude': 39.720}
    with patch.dict(DEMO_SCENARIO_NODES, {'scenario-demo-a': invalid}):
        at.radio(key='active_page').set_value(PAGES[3]); at.run(timeout=90)
        assert not at.exception and at.error
        assert not values(at), 'Route error left stale estimates'
        assert not at.number_input
        at.radio(key='active_page').set_value(PAGES[4]); at.run(timeout=90)
        assert not values(at) and not at.number_input
    at.radio(key='active_page').set_value(PAGES[3]); at.run(timeout=90)
    at.multiselect(key='marine_route_stops_scenario').set_value([])
    at.run(timeout=90)
    assert not at.exception and not at.error and not values(at) and not at.number_input
    after = hashlib.sha256(records.read_bytes()).hexdigest() if records.is_file() else None
    assert before == after
    print(json.dumps({'status': 'passed', 'checked': ['blank input', 'changed consumption', 'equal routes', 'invalid consumption', 'cleared input', 'route error', 'no route'], 'user_records_unchanged': True}))


if __name__ == '__main__':
    main()
