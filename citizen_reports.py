"""Anonymous, insert-only citizen report transport. No privileged key is used."""

import base64
import binascii
import json
import math
import os
import tomllib
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
MAX_PHOTO_BYTES = 5 * 1024 * 1024
BUCKET = 'citizen-reports'
SETUP_MESSAGE = (
    "Supabase kurulumu hazır değil. Sunucudaki .streamlit/secrets.toml dosyasında "
    "Supabase URL ve anonim/publishable anahtarı tanımlayın; ardından "
    "supabase/schema.sql dosyasını Supabase SQL Editor'da çalıştırın."
)


class ReportError(Exception):
    """Only safe, user-facing messages belong in this exception."""


@dataclass(frozen=True)
class SupabaseConfig:
    url: str = field(repr=False)
    public_key: str = field(repr=False)


def is_public_key(value):
    if not isinstance(value, str):
        return False
    if value.startswith('sb_publishable_'):
        return len(value) > len('sb_publishable_')
    try:
        parts = value.split('.')
        if len(parts) != 3:
            return False
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + '=' * (-len(parts[1]) % 4)))
        return isinstance(claims, dict) and claims.get('role') == 'anon'
    except (ValueError, UnicodeError, binascii.Error):
        return False


def load_supabase_config(path=ROOT / '.streamlit' / 'secrets.toml'):
    try:
        with Path(path).open('rb') as handle:
            data = tomllib.load(handle)
        section = data.get('supabase', data.get('SUPABASE', {}))
        if not isinstance(section, dict):
            section = {}
        url = section.get('url') or section.get('SUPABASE_URL') or data.get('SUPABASE_URL')
        url = url.strip() if isinstance(url, str) else url
        candidates = [section.get(x) for x in ('anon_key', 'publishable_key', 'key')]
        candidates += [data.get('SUPABASE_ANON_KEY'), data.get('SUPABASE_PUBLISHABLE_KEY')]
        candidates = [x.strip() if isinstance(x, str) else x for x in candidates]
        key = next((x for x in candidates if is_public_key(x)), None)
        parts = urlsplit(url) if isinstance(url, str) else None
        if (parts is None or parts.scheme != 'https' or not parts.hostname or parts.username
                or parts.password or parts.query or parts.fragment
                or parts.path.rstrip('/') not in ('', '/rest/v1', '/storage/v1', '/auth/v1') or key is None):
            raise ValueError('invalid configuration')
        # Accept known Supabase API endpoints as well as the project root URL.
        return SupabaseConfig(f'{parts.scheme}://{parts.netloc}', key)
    except (OSError, ValueError, TypeError):
        # Never interpolate configuration values, decoder errors, URLs or keys.
        raise ReportError(SETUP_MESSAGE) from None


def load_supabase_env_config(environ=None):
    """Load only the public client key from server process environment.

    This is the production citizen-server path; it deliberately does not read
    Streamlit secrets or accept service-role/secret keys.
    """
    values = os.environ if environ is None else environ
    try:
        url = values.get('SUPABASE_URL')
        key = values.get('SUPABASE_ANON_KEY') or values.get('SUPABASE_PUBLISHABLE_KEY')
        url = url.strip() if isinstance(url, str) else url
        key = key.strip() if isinstance(key, str) else key
        parts = urlsplit(url) if isinstance(url, str) else None
        if (parts is None or parts.scheme != 'https' or not parts.hostname or parts.username
                or parts.password or parts.query or parts.fragment
                or parts.path.rstrip('/') not in ('', '/rest/v1', '/storage/v1', '/auth/v1')
                or not is_public_key(key)):
            raise ValueError('invalid environment configuration')
        return SupabaseConfig(f'{parts.scheme}://{parts.netloc}', key)
    except (ValueError, TypeError):
        raise ReportError(SETUP_MESSAGE) from None


def finite_number(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ReportError(f'{label} geçerli bir sayı olmalıdır.')
    if not low <= value <= high:
        raise ReportError(f'{label} izin verilen aralığın dışında.')
    return float(value)


def validate_report(payload):
    if not isinstance(payload, dict) or payload.get('location_confirmed') is not True:
        raise ReportError('Önce haritadaki konumu açıkça onaylayın.')
    latitude = finite_number(payload.get('latitude'), -90, 90, 'Enlem')
    longitude = finite_number(payload.get('longitude'), -180, 180, 'Boylam')
    source = payload.get('location_source')
    accuracy = payload.get('accuracy_m')
    if source == 'browser_geolocation':
        accuracy = finite_number(accuracy, 0, 40_000_000, 'GPS doğruluk yarıçapı')
    elif source == 'manual_map':
        if accuracy is not None:
            raise ReportError('Manuel seçim için GPS doğruluğu bilinmez; accuracy_m boş olmalıdır.')
    else:
        raise ReportError('Konum kaynağı geçersiz.')
    try:
        captured = datetime.fromisoformat(payload['captured_at'].replace('Z', '+00:00'))
        if captured.tzinfo is None:
            raise ValueError()
        captured_at = captured.astimezone(timezone.utc).isoformat()
    except (KeyError, AttributeError, ValueError, OverflowError):
        raise ReportError('Konum zaman bilgisi geçersiz veya saat dilimi eksik.') from None
    note = payload.get('note', '')
    if not isinstance(note, str) or len(note) > 1000 or '\x00' in note:
        raise ReportError('Not en fazla 1000 karakter olmalıdır.')
    encoded = payload.get('photo_base64')
    if not isinstance(encoded, str) or len(encoded) > (MAX_PHOTO_BYTES * 4 // 3 + 4):
        raise ReportError('En fazla 5 MiB boyutunda bir fotoğraf seçin.')
    try:
        photo = base64.b64decode(encoded, validate=True)
        if not photo or len(photo) > MAX_PHOTO_BYTES:
            raise ValueError()
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(photo)) as image:
                if image.format not in ('JPEG', 'PNG', 'WEBP') or image.width * image.height > 20_000_000:
                    raise ValueError()
                image = ImageOps.exif_transpose(image).convert('RGB')
                image.thumbnail((2048, 2048))
                output = BytesIO()
                image.save(output, format='JPEG', quality=88)
                photo = output.getvalue()  # Strip EXIF; never write the upload to disk.
    except (ValueError, OSError, binascii.Error, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ReportError('Fotoğraf okunamadı. JPEG, PNG veya WebP; en fazla 5 MiB / 20 megapiksel kullanın.') from None
    return dict(note=note.strip(), latitude=latitude, longitude=longitude, accuracy_m=accuracy,
                captured_at=captured_at, location_source=source, status='pending_review'), photo


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Do not forward credentials to redirected hosts.


def supabase_post(config, path, body, content_type, extra_headers=None):
    headers = {'apikey': config.public_key, 'Content-Type': content_type}
    if not config.public_key.startswith('sb_publishable_'):
        headers['Authorization'] = 'Bearer ' + config.public_key
    headers.update(extra_headers or {})
    request = Request(config.url + path, data=body, headers=headers, method='POST')
    try:
        with build_opener(NoRedirect).open(request, timeout=15) as response:
            if not 200 <= response.status < 300:
                raise ReportError('Supabase isteği tamamlanamadı.')
    except (HTTPError, URLError, TimeoutError, OSError):
        # Upstream response bodies can echo private metadata; keep them out of logs/UI.
        raise ReportError('Supabase isteği başarısız. Şema, bucket, RLS ve ağ bağlantısını kontrol edin.') from None


def submit_report(config, payload, transport=supabase_post):
    metadata, photo = validate_report(payload)
    report_id = str(uuid4())
    path = f'{report_id}/photo.jpg'
    metadata.update(id=report_id, photo_path=path)
    try:
        transport(config, f'/storage/v1/object/{BUCKET}/{path}', photo, 'image/jpeg', {'x-upsert': 'false'})
    except ReportError:
        raise ReportError('Fotoğraf yüklenemedi; bildirim kaydedilmedi. Supabase bucket/RLS kurulumunu ve bağlantıyı kontrol edin.') from None
    try:
        transport(config, '/rest/v1/citizen_reports', json.dumps(metadata).encode(),
                  'application/json', {'Prefer': 'return=minimal'})
    except ReportError:
        raise ReportError(
            f'Fotoğraf yüklendi ancak bildirim kaydı tamamlanamadı. Tekrar göndermeden yöneticinize '
            f'bu referansı iletin: {report_id}. Yetim fotoğraf için yönetici kontrolü gerekir.'
        ) from None
    return dict(report_id=report_id, status='pending_review')
