"""Server-side, read-only admin transport for citizen reports.

The service-role key is accepted only in the Streamlit server process. It is
never returned to widgets, the browser, logs, or error messages.
"""

from __future__ import annotations

import json
import base64
import math
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime


class CitizenAdminError(RuntimeError):
    pass


SETUP_MESSAGE = (
    "Vatandaş bildirimlerini okumak için Streamlit sunucusunda Supabase URL ve "
    "yalnızca sunucu tarafında kullanılacak SUPABASE_SERVICE_ROLE_KEY ayarlayın. "
    "Bu anahtarı tarayıcıya koymayın; .streamlit/secrets.toml dosyasını kullanın."
)


@dataclass(frozen=True)
class AdminConfig:
    url: str
    service_role_key: str = ""

    def __repr__(self):
        return "AdminConfig(url=<redacted>, service_role_key=<redacted>)"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def _pick(values, *names):
    for name in names:
        value = values.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def load_admin_config(secrets=None) -> AdminConfig:
    """Read only the server-side admin settings from st.secrets-like data."""
    if secrets is None:
        raise CitizenAdminError(SETUP_MESSAGE)
    try:
        section = secrets.get("supabase", {})
        if not hasattr(section, "get"):
            section = {}
        url = _pick(section, "url", "SUPABASE_URL") or _pick(secrets, "SUPABASE_URL")
        key = _pick(
            section,
            "service_role_key",
            "SUPABASE_SERVICE_ROLE_KEY",
            "service_role",
        ) or _pick(secrets, "SUPABASE_SERVICE_ROLE_KEY")
    except Exception as error:
        raise CitizenAdminError(SETUP_MESSAGE) from error
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise CitizenAdminError(SETUP_MESSAGE)
    if not _is_service_key(key):
        raise CitizenAdminError(SETUP_MESSAGE)
    return AdminConfig(f"{parsed.scheme}://{parsed.netloc}", key)


def _is_service_key(key: str) -> bool:
    lowered = key.lower()
    if "service_role" in lowered or lowered.startswith("sb_secret_"):
        return True
    # Legacy Supabase service keys are JWTs whose payload role is service_role;
    # the literal role is not present in the token's encoded text.
    parts = key.split(".")
    if len(parts) != 3:
        return False
    try:
        padding = "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + padding).decode("utf-8"))
    except (ValueError, UnicodeError, TypeError):
        return False
    return payload.get("role") == "service_role"


def _request(config: AdminConfig, path: str, *, query="", timeout=15):
    url = f"{config.url}{path}{query}"
    request = urllib.request.Request(
        url,
        headers={
            "apikey": config.service_role_key,
            "Authorization": f"Bearer {config.service_role_key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        opener = urllib.request.build_opener(_NoRedirect)
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise CitizenAdminError("Supabase bağlantısı kurulamadı; URL, ağ ve anahtarı kontrol edin.") from error
    except Exception as error:
        raise CitizenAdminError("Supabase yönetici isteği tamamlanamadı.") from error


def _parse_json(data):
    try:
        value = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeError) as error:
        raise CitizenAdminError("Supabase yanıtı okunamadı.") from error
    if not isinstance(value, list):
        raise CitizenAdminError("Supabase vatandaş bildirimleri yanıtı beklenen biçimde değil.")
    return value


def fetch_pending_reports(config: AdminConfig):
    query = "?status=eq.pending_review&order=captured_at.desc"
    status, body = _request(config, "/rest/v1/citizen_reports", query=query)
    if status != 200:
        raise CitizenAdminError("Vatandaş bildirimleri okunamadı; tablo ve yönetici erişimini kontrol edin.")
    rows = []
    for raw in _parse_json(body):
        if not isinstance(raw, dict):
            continue
        try:
            lat = float(raw["latitude"]); lon = float(raw["longitude"])
            if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            accuracy = raw.get("accuracy_m")
            accuracy = None if accuracy is None else float(accuracy)
            if accuracy is not None and (not math.isfinite(accuracy) or accuracy < 0):
                continue
            captured = str(raw.get("captured_at", ""))
            datetime.fromisoformat(captured.replace("Z", "+00:00"))
            rows.append({
                "id": str(raw.get("id", "")), "photo_path": str(raw.get("photo_path", "")),
                "note": str(raw.get("note", "")), "latitude": lat, "longitude": lon,
                "accuracy_m": accuracy, "captured_at": captured,
                "location_source": str(raw.get("location_source", "")),
                "status": str(raw.get("status", "pending_review")),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return rows


def fetch_photo(config: AdminConfig, photo_path: str):
    # The path is returned by Supabase metadata; reject traversal before use.
    if not photo_path or ".." in photo_path or not photo_path.endswith("/photo.jpg"):
        raise CitizenAdminError("Vatandaş fotoğraf yolu geçersiz.")
    safe_path = "/".join(urllib.parse.quote(part, safe="") for part in photo_path.split("/"))
    status, body = _request(config, f"/storage/v1/object/citizen-reports/{safe_path}")
    if status != 200:
        raise CitizenAdminError("Vatandaş fotoğrafı okunamadı; özel bucket erişimini kontrol edin.")
    return body


def is_image_bytes(data: bytes) -> bool:
    return bool(data and data[:2] == b"\xff\xd8" or data[:8] == b"\x89PNG\r\n\x1a\n")
