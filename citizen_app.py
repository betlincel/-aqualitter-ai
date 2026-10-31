"""Standalone citizen page: python citizen_app.py --port 8502 (HTTPS proxy for QR use)."""

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from citizen_reports import ReportError, load_supabase_env_config, submit_report

STATIC = Path(__file__).resolve().parent / 'citizen_web'
MAX_REQUEST_BYTES = 7 * 1024 * 1024


class CitizenHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(20)

    def log_message(self, *_args):
        pass  # No request bodies, coordinates, notes, IPs or credentials in access logs.

    def respond(self, status, data, content_type='application/json; charset=utf-8'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Permissions-Policy', 'geolocation=(self)')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' https://unpkg.com; "
                         "style-src 'self' 'unsafe-inline' https://unpkg.com; img-src 'self' data: blob: https://*.basemaps.cartocdn.com https://unpkg.com; "
                         "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(data)

    def json_response(self, status, payload):
        self.respond(status, json.dumps(payload, ensure_ascii=False).encode())

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/healthz':
            return self.json_response(200, {'ok': True})
        if path == '/api/config':
            try:
                load_supabase_env_config()
                return self.json_response(200, {'ready': True})
            except ReportError as error:
                return self.json_response(200, {'ready': False, 'message': str(error)})
        files = {'/': ('index.html', 'text/html; charset=utf-8'),
                 '/app.js': ('app.js', 'application/javascript; charset=utf-8'),
                 '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if path not in files:
            return self.json_response(404, {'error': 'Sayfa bulunamadı.'})
        name, content_type = files[path]
        self.respond(200, (STATIC / name).read_bytes(), content_type)

    def do_POST(self):
        if self.path != '/api/reports':
            return self.json_response(404, {'error': 'Sayfa bulunamadı.'})
        # Same-origin JSON only. No CORS permission is supplied.
        origin = urlsplit(self.headers.get('Origin', ''))
        if origin.scheme not in ('http', 'https') or origin.netloc != self.headers.get('Host'):
            return self.json_response(403, {'error': 'Bildirimi aynı vatandaş sayfasından gönderin.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = 0
        if self.headers.get_content_type() != 'application/json' or not 0 < length <= MAX_REQUEST_BYTES:
            return self.json_response(400, {'error': 'Gönderim biçimi veya boyutu geçersiz.'})
        try:
            payload = json.loads(self.rfile.read(length))
            result = submit_report(load_supabase_env_config(), payload)
        except (ValueError, UnicodeError):
            return self.json_response(400, {'error': 'Gönderim okunamadı.'})
        except ReportError as error:
            return self.json_response(400, {'error': str(error)})
        except Exception:
            return self.json_response(500, {'error': 'Bildirim tamamlanamadı. Lütfen yöneticiyle iletişime geçin.'})
        self.json_response(201, result)


def main():
    parser = argparse.ArgumentParser(description='AquaLitter vatandaş bildirim prototipi')
    parser.add_argument('--host', default=os.getenv('HOST', '127.0.0.1'))
    parser.add_argument('--port', type=int, default=os.getenv('PORT', '8502'))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), CitizenHandler)
    print(f'Vatandaş sayfası: http://{args.host}:{args.port} (QR/telefon için HTTPS gerekir)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
