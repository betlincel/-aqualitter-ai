"""Read and conservatively check local Trabzon land geometry from a Natural Earth ZIP."""

from __future__ import annotations

import struct
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from math import floor
from math import cos, hypot, radians
from pathlib import Path

from marine_routes import EARTH_RADIUS_KM


# (minimum latitude, minimum longitude, maximum latitude, maximum longitude)
TRABZON_BOUNDS = (40.98, 39.65, 41.08, 39.86)
MIN_COAST_CLEARANCE_KM = 1.0


def _point_in_ring(point: tuple[float, float], ring: list[tuple[float, float]]) -> bool:
    latitude, longitude = point
    inside = False
    for (lat1, lon1), (lat2, lon2) in zip(ring, ring[1:] + ring[:1]):
        if _point_on_segment(point, (lat1, lon1), (lat2, lon2)):
            return True
        if (lat1 > latitude) != (lat2 > latitude):
            crossing_lon = (lon2 - lon1) * (latitude - lat1) / (lat2 - lat1) + lon1
            if longitude < crossing_lon:
                inside = not inside
    return inside


def _point_on_segment(
    point: tuple[float, float],
    first: tuple[float, float],
    second: tuple[float, float],
) -> bool:
    lat, lon = point
    lat1, lon1 = first
    lat2, lon2 = second
    cross = (lon - lon1) * (lat2 - lat1) - (lat - lat1) * (lon2 - lon1)
    if abs(cross) > 1e-10:
        return False
    return (
        min(lat1, lat2) - 1e-10 <= lat <= max(lat1, lat2) + 1e-10
        and min(lon1, lon2) - 1e-10 <= lon <= max(lon1, lon2) + 1e-10
    )


def _segments_intersect(a, b, c, d) -> bool:
    def orientation(p, q, r):
        return (q[1] - p[1]) * (r[0] - p[0]) - (q[0] - p[0]) * (r[1] - p[1])

    o1 = orientation(a, b, c)
    o2 = orientation(a, b, d)
    o3 = orientation(c, d, a)
    o4 = orientation(c, d, b)
    if ((o1 > 0 and o2 < 0) or (o1 < 0 and o2 > 0)) and (
        (o3 > 0 and o4 < 0) or (o3 < 0 and o4 > 0)
    ):
        return True
    return (
        (abs(o1) <= 1e-10 and _point_on_segment(c, a, b))
        or (abs(o2) <= 1e-10 and _point_on_segment(d, a, b))
        or (abs(o3) <= 1e-10 and _point_on_segment(a, c, d))
        or (abs(o4) <= 1e-10 and _point_on_segment(b, c, d))
    )


def _xy_km(point: tuple[float, float], latitude_origin: float) -> tuple[float, float]:
    latitude, longitude = point
    x = radians(longitude) * EARTH_RADIUS_KM * cos(radians(latitude_origin))
    y = radians(latitude) * EARTH_RADIUS_KM
    return x, y


def _point_segment_distance_km(point, first, second, latitude_origin: float) -> float:
    px, py = _xy_km(point, latitude_origin)
    ax, ay = _xy_km(first, latitude_origin)
    bx, by = _xy_km(second, latitude_origin)
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom == 0:
        return hypot(px - ax, py - ay)
    ratio = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    return hypot(px - (ax + ratio * dx), py - (ay + ratio * dy))


def _segment_distance_km(a, b, c, d) -> float:
    latitude_origin = (a[0] + b[0] + c[0] + d[0]) / 4
    if _segments_intersect(a, b, c, d):
        return 0.0
    return min(
        _point_segment_distance_km(a, c, d, latitude_origin),
        _point_segment_distance_km(b, c, d, latitude_origin),
        _point_segment_distance_km(c, a, b, latitude_origin),
        _point_segment_distance_km(d, a, b, latitude_origin),
    )


@dataclass
class LandMask:
    """Local land polygons, each represented as rings of (latitude, longitude)."""

    shapes: list[list[list[tuple[float, float]]]]
    bounds: tuple[float, float, float, float] = TRABZON_BOUNDS
    clearance_km: float = MIN_COAST_CLEARANCE_KM
    _latitude_bucket_size: float = field(default=0.01, init=False, repr=False)

    def __post_init__(self):
        """Index only latitude-crossing edges and coastline segments near the region."""
        min_lat, min_lon, max_lat, max_lon = self.bounds
        lat_margin = self.clearance_km / 110.5 + 1e-9
        lon_margin = self.clearance_km / (111.0 * cos(radians(max(abs(min_lat), abs(max_lat))))) + 1e-9
        self._point_edges_by_band = defaultdict(list)
        self._local_coast_edges = []
        step = self._latitude_bucket_size

        for shape_index, rings in enumerate(self.shapes):
            for ring_index, ring in enumerate(rings):
                for first, second in zip(ring, ring[1:] + ring[:1]):
                    y1, x1 = first
                    y2, x2 = second
                    edge = (shape_index, ring_index, first, second)
                    low_y, high_y = min(y1, y2), max(y1, y2)
                    if high_y >= min_lat and low_y <= max_lat:
                        first_band = floor(max(low_y, min_lat) / step)
                        last_band = floor(min(high_y, max_lat) / step)
                        for band in range(first_band, last_band + 1):
                            self._point_edges_by_band[band].append(edge)

                    if not (
                        max(x1, x2) < min_lon - lon_margin
                        or min(x1, x2) > max_lon + lon_margin
                        or max(y1, y2) < min_lat - lat_margin
                        or min(y1, y2) > max_lat + lat_margin
                    ):
                        self._local_coast_edges.append((first, second))

    @classmethod
    def from_geojson(cls, geojson: dict, **kwargs) -> "LandMask":
        """Construct from GeoJSON geometry; useful for fixtures and local clipped files."""
        shapes = []
        for feature in geojson.get("features", []):
            geometry = feature.get("geometry") or {}
            kind = geometry.get("type")
            coordinates = geometry.get("coordinates", [])
            polygons = [coordinates] if kind == "Polygon" else coordinates if kind == "MultiPolygon" else []
            for polygon in polygons:
                rings = [
                    [(float(lat), float(lon)) for lon, lat, *_ in ring]
                    for ring in polygon
                    if len(ring) >= 4
                ]
                if rings:
                    shapes.append(rings)
        return cls(shapes=shapes, **kwargs)

    def _inside_land(self, point: tuple[float, float]) -> bool:
        # A ray crossing test is exact, but examines only edges near this latitude.
        # Per-ring parity retains the even/odd hole handling of the original method.
        latitude, longitude = point
        band = floor(latitude / self._latitude_bucket_size)
        ring_parity = defaultdict(bool)
        for shape_index, ring_index, first, second in self._point_edges_by_band.get(band, ()):
            if _point_on_segment(point, first, second):
                return True
            lat1, lon1 = first
            lat2, lon2 = second
            if (lat1 > latitude) != (lat2 > latitude):
                crossing_lon = (lon2 - lon1) * (latitude - lat1) / (lat2 - lat1) + lon1
                if longitude < crossing_lon:
                    key = (shape_index, ring_index)
                    ring_parity[key] = not ring_parity[key]
        shape_parity = defaultdict(bool)
        for (shape_index, _ring_index), inside_ring in ring_parity.items():
            if inside_ring:
                shape_parity[shape_index] = not shape_parity[shape_index]
        return any(shape_parity.values())

    def validate_path(self, points: list[tuple[float, float]]) -> str | None:
        """Return a reason when a point/path is outside bounds, on land, or too close."""
        if not points:
            return "Rota geometrisi boş."
        min_lat, min_lon, max_lat, max_lon = self.bounds
        for latitude, longitude in points:
            if not (min_lat <= latitude <= max_lat and min_lon <= longitude <= max_lon):
                return "Trabzon denetim bölgesinin dışında."
            if self._inside_land((latitude, longitude)):
                return "Nokta kara poligonu içinde veya kıyı sınırında."

        path_segments = list(zip(points, points[1:]))
        if not path_segments:
            path_segments = [(points[0], points[0])]
        for start, end in path_segments:
            midpoint = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
            if self._inside_land(midpoint):
                return "Bağlantı kara poligonuyla kesişiyor."
            path_min_lat, path_max_lat = sorted((start[0], end[0]))
            path_min_lon, path_max_lon = sorted((start[1], end[1]))
            for coast_start, coast_end in self._local_coast_edges:
                if (
                    max(coast_start[0], coast_end[0]) < path_min_lat - self.clearance_km / 110.5
                    or min(coast_start[0], coast_end[0]) > path_max_lat + self.clearance_km / 110.5
                    or max(coast_start[1], coast_end[1]) < path_min_lon - self.clearance_km / (111.0 * cos(radians(42.0)))
                    or min(coast_start[1], coast_end[1]) > path_max_lon + self.clearance_km / (111.0 * cos(radians(42.0)))
                ):
                    continue
                if _segments_intersect(start, end, coast_start, coast_end):
                    return "Bağlantı kara kıyı sınırıyla kesişiyor."
                if _segment_distance_km(start, end, coast_start, coast_end) < self.clearance_km:
                    return (
                        f"Kıyıya {self.clearance_km:.1f} km güvenlik "
                        "tamponundan daha yakın."
                    )
        return None


def _read_local_shapes(
    shp_bytes: bytes,
    bounds: tuple[float, float, float, float],
) -> list[list[list[tuple[float, float]]]]:
    if len(shp_bytes) < 100 or struct.unpack_from(">i", shp_bytes, 0)[0] != 9994:
        raise ValueError("ZIP içinde geçerli ESRI Shapefile bulunamadı.")
    min_lat, min_lon, max_lat, max_lon = bounds
    shapes = []
    offset = 100
    while offset + 8 <= len(shp_bytes):
        _record_number, content_words = struct.unpack_from(">2i", shp_bytes, offset)
        offset += 8
        content_length = content_words * 2
        content = shp_bytes[offset : offset + content_length]
        offset += content_length
        if len(content) < 44:
            continue
        shape_type = struct.unpack_from("<i", content, 0)[0]
        if shape_type not in (5, 15, 25):  # Polygon, PolygonZ, PolygonM
            continue
        xmin, ymin, xmax, ymax = struct.unpack_from("<4d", content, 4)
        if xmax < min_lon or xmin > max_lon or ymax < min_lat or ymin > max_lat:
            continue
        part_count, point_count = struct.unpack_from("<2i", content, 36)
        if part_count < 1 or point_count < 4:
            continue
        parts_offset = 44
        part_starts = struct.unpack_from(f"<{part_count}i", content, parts_offset)
        points_offset = parts_offset + 4 * part_count
        raw_points = [
            struct.unpack_from("<2d", content, points_offset + 16 * index)
            for index in range(point_count)
        ]
        starts = [*part_starts, point_count]
        rings = []
        for index in range(part_count):
            ring = [(lat, lon) for lon, lat in raw_points[starts[index] : starts[index + 1]]]
            if len(ring) >= 4:
                rings.append(ring)
        if rings:
            shapes.append(rings)
    return shapes


def load_natural_earth_zip(
    zip_path: str | Path,
    bounds: tuple[float, float, float, float] = TRABZON_BOUNDS,
    clearance_km: float = MIN_COAST_CLEARANCE_KM,
) -> LandMask:
    """Load the official Natural Earth land shapefile directly from its ZIP."""
    zip_path = Path(zip_path)
    if not zip_path.is_file():
        raise FileNotFoundError(f"Kıyı denetim verisi bulunamadı: {zip_path}")
    try:
        with zipfile.ZipFile(zip_path) as archive:
            shp_name = next(
                (name for name in archive.namelist() if name.lower().endswith(".shp")),
                None,
            )
            if shp_name is None:
                raise ValueError("ZIP içinde .shp kara poligonu yok.")
            prj_name = next(
                (name for name in archive.namelist() if name.lower().endswith(".prj")),
                None,
            )
            if prj_name is not None:
                projection = archive.read(prj_name).decode("utf-8", errors="ignore").lower()
                if "wgs_1984" not in projection and "wgs 84" not in projection:
                    raise ValueError("Kıyı poligonu WGS84/CRS84 koordinat sisteminde değil.")
            shapes = _read_local_shapes(archive.read(shp_name), bounds)
    except zipfile.BadZipFile as error:
        raise ValueError("Kıyı verisi ZIP dosyası bozuk veya tamamlanmamış.") from error
    if not shapes:
        raise ValueError("Trabzon denetim bölgesinde kara poligonu bulunamadı.")
    return LandMask(shapes=shapes, bounds=bounds, clearance_km=clearance_km)
