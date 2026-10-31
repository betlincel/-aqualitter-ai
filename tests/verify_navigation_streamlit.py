"""Controlled UI state fixtures only: no model output/performance claims or record writes."""

import ast
import hashlib
import json
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image
from streamlit.testing.v1 import AppTest
from marine_routes import DEMO_SCENARIO_NODES
from ui_shell import PAGES


def navigate(at, page):
    at.radio(key='active_page').set_value(page)
    at.run(timeout=90)
    assert not at.exception, [str(x) for x in at.exception]


def main():
    records = ROOT / 'data' / 'confirmed_observations.json'
    before = hashlib.sha256(records.read_bytes()).hexdigest()
    # Synthetic state fixture, used solely to exercise the unchanged review widgets.
    image = BytesIO()
    Image.new('RGB', (64, 64), '#123456').save(image, format='PNG')
    photo = image.getvalue()
    image_hash = hashlib.sha256(photo).hexdigest()
    syntax = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))
    labels = next(ast.literal_eval(x.value) for x in syntax.body if isinstance(x, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == 'PROMPT_LABELS' for t in x.targets))
    prompt = '. '.join(labels) + '.'
    analysis_id = hashlib.sha256(f'{image_hash}|0.30|{prompt}'.encode()).hexdigest()
    raw = [{
        'İfade (İngilizce)': label, 'Modelin ham ifadesi': label,
        'Model güven puanı': .8, 'Kutu (x1, y1, x2, y2) px': '5, 5, 30, 30',
        'box': (5, 5, 30, 30),
    } for label in ('fixture a', 'fixture b')]
    candidate = {**raw[0], 'label_variants': ['fixture a', 'fixture b'],
                 'raw_indices': [0, 1], 'raw_count': 2, 'primary_raw_index': 0,
                 'candidate_id': 'navigation-fixture', 'detection_id': 'fixture-box'}
    analysis = dict(image_sha256=image_hash, image_width=64, image_height=64, threshold=.3,
                    raw_candidates=raw, review_candidates=[candidate])
    selected = list(DEMO_SCENARIO_NODES)
    order_key = 'marine_visit_order_' + hashlib.sha1(('Senaryo|' + '|'.join(selected)).encode()).hexdigest()[:10]
    at = AppTest.from_file(str(ROOT / 'app.py'))
    at.session_state['active_page'] = PAGES[1]
    at.session_state['active_photo'] = dict(name='controlled-state-fixture.png', bytes=photo)
    at.session_state['analysis_threshold'] = .3
    at.session_state['analysis_runs'] = {analysis_id: analysis}
    at.session_state['marine_route_stops_scenario'] = selected
    at.session_state[order_key] = tuple(f'scenario-demo-{x}' for x in 'fbdace')
    at.run(timeout=90)
    assert not at.exception and not at.error
    at.radio(key='review_decision_navigation-fixture').set_value('Reddet')
    at.selectbox(key='review_label_navigation-fixture').set_value('fixture b')
    at.run(timeout=90)

    navigate(at, PAGES[2])
    observation_id = at.selectbox(key='map_edit_observation_id').value
    at.radio(key=f'location_method_{observation_id}').set_value('Haritada seç')
    at.text_input(key=f'observation_date_{observation_id}').set_value('2026-10-30')
    with patch('streamlit_folium.st_folium', return_value={'last_clicked': {'lat': 41.060, 'lng': 39.750}}):
        at.run(timeout=90)
    with patch('streamlit_folium.st_folium', return_value={'last_clicked': {'lat': 41.064, 'lng': 39.760}}):
        at.run(timeout=90)
    expected_location = dict(latitude=41.064, longitude=39.760)
    assert at.session_state[f'map_click_{observation_id}'] == expected_location

    navigate(at, PAGES[3])
    assert not at.error and at.status[0].state == 'complete'
    assert at.multiselect(key='marine_route_stops_scenario').value == selected
    assert at.selectbox(key=order_key).value == tuple(f'scenario-demo-{x}' for x in 'fbdace')
    snapshot = at.session_state['route_snapshot']
    assert abs(snapshot['optimized']['current_km'] - 64.37911378355338) < 1e-9
    navigate(at, PAGES[4])
    at.number_input(key='marine_fuel_consumption').set_value(2.0)
    at.run(timeout=90)
    assert not at.error and not at.exception
    navigate(at, PAGES[0])
    metrics = {x.label: x.value for x in at.metric}
    assert metrics['Önerilen rota'] == '39.22 km'
    assert metrics['Tahmini CO₂ farkı'] == '73.28 kg'
    navigate(at, PAGES[1])
    assert at.radio(key='review_decision_navigation-fixture').value == 'Reddet'
    assert at.selectbox(key='review_label_navigation-fixture').value == 'fixture b'
    assert at.session_state['active_photo']['bytes'] == photo
    assert at.session_state['analysis_runs'][analysis_id] == analysis
    navigate(at, PAGES[2])
    assert at.session_state[f'map_click_{observation_id}'] == expected_location
    assert at.text_input(key=f'observation_date_{observation_id}').value == '2026-10-30'
    navigate(at, PAGES[3])
    assert not at.error and at.status[0].state == 'complete'
    navigate(at, PAGES[4])
    assert at.number_input(key='marine_fuel_consumption').value == 2.0
    # Current inputs invalidate estimates and overview cards when visits are cleared.
    navigate(at, PAGES[3])
    at.multiselect(key='marine_route_stops_scenario').set_value([]); at.run(timeout=90)
    navigate(at, PAGES[0])
    metrics = {x.label: x.value for x in at.metric}
    assert metrics['Önerilen rota'] == 'Henüz hesaplanmadı'
    assert metrics['Tahmini CO₂ farkı'] == 'Henüz hesaplanmadı'
    assert before == hashlib.sha256(records.read_bytes()).hexdigest()
    print(json.dumps({'status': 'passed', 'photo_and_analysis_retained': True,
                      'review_decisions_retained': True, 'map_click_and_date_retained': True,
                      'route_and_consumption_retained': True, 'overview_matches_data': True,
                      'records_unchanged': True, 'inference_tested': False}))


if __name__ == '__main__':
    main()
