import base64
import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image
from citizen_app import CitizenHandler
from citizen_reports import (
    ReportError, SETUP_MESSAGE, SupabaseConfig, is_public_key,
    load_supabase_config, load_supabase_env_config, submit_report, validate_report,
)
from citizen_admin import CitizenAdminError, AdminConfig, fetch_pending_reports, fetch_photo, load_admin_config


def payload():
    image = BytesIO()
    Image.new('RGB', (32, 24), '#146e44').save(image, 'PNG')
    return dict(latitude=41.0612345, longitude=39.7567891, accuracy_m=12.5,
                captured_at='2026-10-31T12:34:56.789Z', location_source='browser_geolocation',
                location_confirmed=True, note=' Test ', photo_base64=base64.b64encode(image.getvalue()).decode())


def fake_jwt(role):
    claims = base64.urlsafe_b64encode(json.dumps({'role': role}).encode()).decode().rstrip('=')
    return f'fixture.{claims}.fixture'


class CitizenReportTests(unittest.TestCase):
    def test_admin_config_accepts_service_role_jwt_without_exposing_it(self):
        service = fake_jwt('service_role')
        config = load_admin_config({'supabase': {'url': 'https://example.supabase.co', 'service_role_key': service}})
        self.assertEqual(config.url, 'https://example.supabase.co')
        self.assertNotIn(service, repr(config))
        with self.assertRaises(CitizenAdminError):
            load_admin_config({'supabase': {'url': 'https://example.supabase.co', 'anon_key': fake_jwt('anon')}})

    def test_admin_pending_rows_and_photo_use_server_transport(self):
        class Response:
            def __init__(self, body): self.status, self.body = 200, body
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self): return self.body
        row = {'id': 'citizen-1', 'photo_path': 'citizen-1/photo.jpg', 'note': 'şişe',
               'latitude': 40.991415, 'longitude': 39.775618, 'accuracy_m': 129,
               'captured_at': '2026-10-31T10:00:00+00:00', 'location_source': 'browser_geolocation',
               'status': 'pending_review'}
        responses = [Response(json.dumps([row]).encode()), Response(b'\xff\xd8fixture')]
        class Opener:
            def open(self, *_args, **_kwargs): return responses.pop(0)
        with patch('citizen_admin.urllib.request.build_opener', return_value=Opener()) as build:
            config = AdminConfig('https://example.supabase.co', fake_jwt('service_role'))
            reports = fetch_pending_reports(config)
            photo = fetch_photo(config, reports[0]['photo_path'])
        self.assertEqual((reports[0]['latitude'], reports[0]['longitude']), (40.991415, 39.775618))
        self.assertEqual(reports[0]['accuracy_m'], 129.0)
        self.assertEqual(photo, b'\xff\xd8fixture')
        self.assertEqual(build.call_count, 2)
    def test_missing_config_is_clear_and_privileged_keys_are_rejected(self):
        with self.assertRaisesRegex(ReportError, 'Supabase kurulumu'):
            load_supabase_config(Path(tempfile.gettempdir()) / 'missing-citizen-fixture.toml')
        self.assertFalse(is_public_key(fake_jwt('service_role')))
        self.assertFalse(is_public_key('sb_secret_fixture'))
        self.assertTrue(is_public_key(fake_jwt('anon')))
        self.assertTrue(is_public_key('sb_publishable_fixture'))
        config = SupabaseConfig('https://example.supabase.co', 'sb_publishable_fixture')
        self.assertNotIn('fixture', repr(config))
        self.assertNotIn('example', repr(config))

    def test_config_reads_server_file_without_echoing_values(self):
        config_data = {'supabase': {'url': ' https://example.supabase.co/rest/v1/ \n', 'anon_key': fake_jwt('anon')}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'secrets.toml'
            path.write_bytes(b'')
            with patch('citizen_reports.tomllib.load', return_value=config_data):
                self.assertEqual(load_supabase_config(path).url, 'https://example.supabase.co')
            config_data['supabase']['anon_key'] = fake_jwt('service_role')
            with patch('citizen_reports.tomllib.load', return_value=config_data):
                with self.assertRaises(ReportError) as error:
                    load_supabase_config(path)
                self.assertEqual(str(error.exception), SETUP_MESSAGE)

    def test_production_env_loader_accepts_public_key_only(self):
        config = load_supabase_env_config({
            'SUPABASE_URL': ' https://example.supabase.co/rest/v1/ ',
            'SUPABASE_ANON_KEY': fake_jwt('anon'),
        })
        self.assertEqual(config.url, 'https://example.supabase.co')
        with self.assertRaises(ReportError):
            load_supabase_env_config({'SUPABASE_URL': 'https://example.supabase.co',
                                      'SUPABASE_ANON_KEY': fake_jwt('service_role')})

    def test_gps_and_manual_keep_exact_coordinates_and_provenance(self):
        data, photo = validate_report(payload())
        self.assertEqual((data['latitude'], data['longitude']), (41.0612345, 39.7567891))
        self.assertEqual(data['accuracy_m'], 12.5)
        self.assertEqual(data['captured_at'], '2026-10-31T12:34:56.789000+00:00')
        self.assertEqual(data['status'], 'pending_review')
        self.assertTrue(photo.startswith(b'\xff\xd8'))
        manual = {**payload(), 'latitude': -12.3456789, 'longitude': 77.1234567,
                  'accuracy_m': None, 'location_source': 'manual_map'}
        result, _ = validate_report(manual)
        self.assertEqual(result['latitude'], manual['latitude'])
        self.assertEqual(result['longitude'], manual['longitude'])
        self.assertIsNone(result['accuracy_m'])

    def test_invalid_or_unconfirmed_inputs_are_rejected(self):
        for change in [dict(location_confirmed=False), dict(latitude=91), dict(longitude=float('nan')),
                       dict(accuracy_m=-1), dict(accuracy_m=None), dict(captured_at='not a time'),
                       dict(captured_at='2026-10-31T12:00:00'), dict(note='x' * 1001),
                       dict(location_source='manual_map'), dict(photo_base64='not-base64')]:
            with self.subTest(change=list(change)), self.assertRaises(ReportError):
                validate_report({**payload(), **change})

    def test_upload_then_insert_is_pending_and_has_no_read_update_delete(self):
        calls = []
        def transport(config, path, body, content_type, headers):
            calls.append((path, body, content_type, headers))
        receipt = submit_report(SupabaseConfig('https://example.supabase.co', 'sb_publishable_fixture'),
                                {**payload(), 'status': 'approved'}, transport)
        self.assertEqual(len(calls), 2)
        self.assertIn('/storage/v1/object/citizen-reports/', calls[0][0])
        self.assertEqual(calls[0][3]['x-upsert'], 'false')
        metadata = json.loads(calls[1][1])
        self.assertEqual(metadata['photo_path'], receipt['report_id'] + '/photo.jpg')
        self.assertEqual(metadata['status'], 'pending_review')
        self.assertEqual(calls[1][3]['Prefer'], 'return=minimal')

    def test_failures_do_not_claim_success_or_require_delete_permission(self):
        calls = []
        def transport(config, path, body, content_type, headers):
            calls.append(path)
            if path == '/rest/v1/citizen_reports':
                raise ReportError('upstream fixture')
        with self.assertRaisesRegex(ReportError, 'Fotoğraf yüklendi ancak bildirim'):
            submit_report(SupabaseConfig('https://example.supabase.co', 'sb_publishable_fixture'), payload(), transport)
        self.assertEqual(len(calls), 2)
        with self.assertRaisesRegex(ReportError, 'Fotoğraf yüklenemedi'):
            submit_report(None, payload(), lambda *_: (_ for _ in ()).throw(ReportError('fixture')))


class CitizenHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), CitizenHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(timeout=2)

    def test_missing_setup_and_assets_expose_no_credentials(self):
        with patch('citizen_app.load_supabase_env_config', side_effect=ReportError(SETUP_MESSAGE)):
            with urlopen(self.url + '/api/config') as response:
                data = json.load(response)
                self.assertFalse(data['ready'])
                self.assertIn('Supabase kurulumu', data['message'])
                self.assertEqual(response.headers['Permissions-Policy'], 'geolocation=(self)')
        with urlopen(self.url + '/') as response:
            page = response.read().decode()
            self.assertIn('Konumumu kullan', page)
            self.assertNotIn('sb_publishable_', page)
            self.assertNotIn('service_role', page)
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + '/.streamlit/secrets.toml')
        self.assertEqual(error.exception.code, 404)

    def test_cross_origin_is_denied_and_valid_json_uses_server_transport(self):
        request = Request(self.url + '/api/reports', data=b'{}',
                          headers={'Content-Type': 'application/json', 'Origin': 'https://other.example'})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 403)
        config = SupabaseConfig('https://example.supabase.co', 'sb_publishable_fixture')
        with patch('citizen_app.load_supabase_env_config', return_value=config), patch(
            'citizen_app.submit_report', return_value={'report_id':'fixture-id','status':'pending_review'}
        ) as send:
            request = Request(self.url + '/api/reports', data=b'{}',
                              headers={'Content-Type': 'application/json', 'Origin': self.url})
            with urlopen(request) as response:
                self.assertEqual(response.status, 201)
                self.assertEqual(json.load(response)['status'], 'pending_review')
            send.assert_called_once_with(config, {})


if __name__ == '__main__':
    unittest.main()
