from __future__ import annotations

import hashlib
import html
import json
import math
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from datetime import date, datetime, timezone
from io import BytesIO
from itertools import permutations
from pathlib import Path
from queue import Empty, Queue
from time import monotonic

import streamlit as st
import torch
import folium
from folium.plugins import PolyLineTextPath
from PIL import Image, ImageDraw, ImageOps
from streamlit_folium import st_folium
from ui_shell import (
    PAGES, preserve_ui_values, shell, go_to, context_badge, capture_upload, clear_photo,
)
from fuel_estimates import (
    DIESEL_KG_CO2_PER_LITER,
    EPA_SOURCE_DATE,
    EPA_SOURCE_URL,
    NIST_SOURCE_URL,
    compare_fuel_co2,
)
from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
from coastline import (
    MIN_COAST_CLEARANCE_KM,
    TRABZON_BOUNDS,
    load_natural_earth_zip,
)
from marine_routes import (
    DEMO_SCENARIO_NODES,
    DEMO_VESSEL_NODES,
    KM_PER_NAUTICAL_MILE,
    RouteNotAvailable,
    build_land_checked_links,
    compare_visit_orders,
    repeated_edge_passes,
)
from citizen_admin import CitizenAdminError, fetch_pending_reports, fetch_photo, load_admin_config


MODEL_ID = "IDEA-Research/grounding-dino-tiny"
MODEL_DIR = Path(__file__).resolve().parent / "models" / "grounding-dino-tiny"
CONFIRMED_FILE = Path(__file__).resolve().parent / "data" / "confirmed_observations.json"
LAND_MASK_FILE = Path(__file__).resolve().parent / "data" / "ne_10m_land.zip"
REQUIRED_MODEL_FILES = (
    "config.json",
    "model.safetensors",
    "preprocessor_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
)
PROMPT_LABELS = (
    "plastic bottle",
    "plastic bag",
    "beverage can",
    "paper cup",
    "food wrapper",
    "litter",
)
# Grounding DINO expects candidate concepts separated by periods.
PROMPT = ". ".join(PROMPT_LABELS) + "."
NO_DETECTIONS = "Bu görüntüde modelin kapsamına giren atık tespit edilmedi"
TRABZON_CENTER = (41.0053, 39.7267)
ESRI_TILE_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/"
    "MapServer/tile/{z}/{y}/{x}"
)
ESRI_TILE_ATTRIBUTION = (
    "Tiles &copy; Esri — Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, "
    "Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community"
)
OSM_DE_TILE_URL = "https://tile.openstreetmap.de/{z}/{x}/{y}.png"
OSM_DE_ATTRIBUTION = "&copy; OpenStreetMap contributors"
# These built-in records are illustrative scenarios, not model/photo observations.
# Coordinates have one source so the observation map and route map cannot drift.
SCENARIO_DEMO_RECORDS = [
    {
        "observation_id": node_id,
        "record_type": "scenario",
        "scenario_label": f"{node['label']} · temsili deniz noktası",
        "observation_date": None,
        "location_source": "scenario_demo",
        "location": {"latitude": node["latitude"], "longitude": node["longitude"]},
        "approved_detections": [{"label": "litter"}],
    }
    for node_id, node in DEMO_SCENARIO_NODES.items()
]


class ModelLoadError(RuntimeError):
    """Raised when the local model files are absent or cannot be loaded."""


def load_model():
    if not MODEL_DIR.is_dir():
        raise ModelLoadError(
            f"Yerel model klasörü bulunamadı: {MODEL_DIR}. "
            "README'deki resmî indirme komutunu çalıştırın."
        )

    missing = [name for name in REQUIRED_MODEL_FILES if not (MODEL_DIR / name).is_file()]
    if missing:
        raise ModelLoadError(
            "Yerel model eksik. Eksik dosyalar: " + ", ".join(missing)
        )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    try:
        processor = AutoProcessor.from_pretrained(
            MODEL_DIR,
            local_files_only=True,
        )
        model = AutoModelForZeroShotObjectDetection.from_pretrained(
            MODEL_DIR,
            use_safetensors=True,
            local_files_only=True,
        )
        model = model.to(device)
        model.eval()
    except Exception as error:
        raise ModelLoadError(
            f"Model/işlemci dosyaları okunamadı ({type(error).__name__}): {error}"
        ) from error

    return processor, model, device


@st.cache_resource(show_spinner="Trabzon kara verisi yükleniyor…")
def load_route_land_mask(
    file_path: str,
    file_mtime_ns: int,
    file_size: int,
    file_sha256: str,
    bounds: tuple[float, float, float, float],
    clearance_km: float,
):
    """Cache prepared geometry; source content and all spatial settings key the cache."""
    return load_natural_earth_zip(
        file_path, bounds=bounds, clearance_km=clearance_km
    )


def normalize_model_label(label: str) -> str:
    """Normalize whitespace/case only; never infer a different class."""
    return " ".join(str(label).casefold().strip(" \t\r\n.,;:").split())


def run_inference(
    image: Image.Image,
    threshold: float,
    processor,
    model,
    device: torch.device,
):
    inputs = processor(images=image, text=PROMPT, return_tensors="pt").to(device)
    with torch.inference_mode():
        outputs = model(**inputs)

    detections = processor.post_process_grounded_object_detection(
        outputs,
        inputs.input_ids,
        threshold=threshold,
        text_threshold=max(0.15, threshold - 0.05),
        # PIL reports (width, height); Transformers expects (height, width).
        target_sizes=[image.size[::-1]],
    )[0]

    boxes = detections["boxes"].detach().cpu().tolist()
    scores = detections["scores"].detach().cpu().tolist()
    labels = detections["text_labels"]
    rows = []
    for box, score, label in zip(boxes, scores, labels):
        x1, y1, x2, y2 = [round(value) for value in box]
        raw_label = str(label)
        rows.append(
            {
                "İfade (İngilizce)": normalize_model_label(raw_label),
                "Modelin ham ifadesi": raw_label,
                "Model güven puanı": float(score),
                "Kutu (x1, y1, x2, y2) px": f"{x1}, {y1}, {x2}, {y2}",
                "box": (x1, y1, x2, y2),
            }
        )
    return rows


def are_duplicate_boxes(
    first: tuple[int, int, int, int], second: tuple[int, int, int, int]
) -> bool:
    """Group only identical pixel-coordinate predictions for review."""
    return first == second


def group_duplicate_candidates(raw_candidates: list[dict]) -> list[dict]:
    """Keep every raw row, grouping identical boxes only for review."""
    groups: list[dict] = []
    for raw_index, candidate in enumerate(raw_candidates):
        group = next(
            (
                item
                for item in groups
                if are_duplicate_boxes(
                    candidate["box"], item["representative"]["box"]
                )
            ),
            None,
        )
        if group is None:
            groups.append(
                {
                    "first_raw_index": raw_index,
                    "members": [(raw_index, candidate)],
                    "representative": candidate,
                }
            )
            continue

        group["members"].append((raw_index, candidate))
        group["representative"] = max(
            group["members"], key=lambda member: member[1]["Model güven puanı"]
        )[1]

    review_candidates = []
    for group in groups:
        members = group["members"]
        representative = dict(group["representative"])
        variants = []
        for _, member in sorted(
            members, key=lambda item: item[1]["Model güven puanı"], reverse=True
        ):
            label = member["İfade (İngilizce)"]
            if label not in variants:
                variants.append(label)
        representative["label_variants"] = variants
        representative["raw_indices"] = [index for index, _ in members]
        representative["raw_count"] = len(members)
        representative["primary_raw_index"] = next(
            index
            for index, member in members
            if member is group["representative"]
        )
        review_candidates.append(representative)
    return review_candidates


def observation_id_for_image(image_sha256: str) -> str:
    return f"obs-{image_sha256[:32]}"


def detection_id_for_box(image_sha256: str, box: tuple[int, int, int, int]) -> str:
    return hashlib.sha256(f"{image_sha256}:{box}".encode("utf-8")).hexdigest()


def migrate_flat_observations(flat_observations: list[dict]) -> list[dict]:
    """Convert schema 1 per-detection rows into one unlocated observation per image."""
    grouped: dict[str, dict] = {}
    for legacy in flat_observations:
        image_sha256 = legacy.get("image_sha256") or legacy.get("observation_id")
        if not image_sha256:
            image_sha256 = hashlib.sha256(
                json.dumps(legacy, sort_keys=True).encode("utf-8")
            ).hexdigest()
        record = grouped.setdefault(
            image_sha256,
            {
                "observation_id": observation_id_for_image(image_sha256),
                "image_sha256": image_sha256,
                "record_type": "unclassified",
                "observation_date": None,
                "date_source": None,
                "location": None,
                "location_source": None,
                "approved_detections": [],
                "legacy_reviewed_at_utc": legacy.get("reviewed_at_utc"),
            },
        )
        box = tuple(legacy.get("bbox_xyxy_pixels", ()))
        detection_id = legacy.get("observation_id") or detection_id_for_box(
            image_sha256, box
        )
        record["approved_detections"].append(
            {
                "detection_id": detection_id,
                "label": legacy.get("label", ""),
                "model_label_variants": legacy.get("model_label_variants", []),
                "model_confidence": legacy.get("model_confidence"),
                "confidence_threshold": legacy.get("confidence_threshold"),
                "bbox_xyxy_pixels": list(box),
                "image_width_pixels": legacy.get("image_width_pixels"),
                "image_height_pixels": legacy.get("image_height_pixels"),
                "model_id": legacy.get("model_id", MODEL_ID),
                "review_status": "confirmed_by_user",
                "reviewed_at_utc": legacy.get("reviewed_at_utc"),
            }
        )
    return list(grouped.values())


def load_observations() -> list[dict]:
    if not CONFIRMED_FILE.exists():
        return []
    payload = json.loads(CONFIRMED_FILE.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("observations"), list):
        raise ValueError("Onay kayıt dosyasının biçimi desteklenmiyor.")
    if payload.get("schema_version") == 1:
        return migrate_flat_observations(payload["observations"])
    if payload.get("schema_version") == 2:
        return payload["observations"]
    raise ValueError("Onay kayıt dosyasının sürümü desteklenmiyor.")


def save_observations(observations: list[dict]) -> None:
    CONFIRMED_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = CONFIRMED_FILE.with_name(CONFIRMED_FILE.name + ".tmp")
    payload = {"schema_version": 2, "observations": observations}
    temporary_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary_file.replace(CONFIRMED_FILE)


def make_approved_detection(
    candidate: dict,
    label: str,
    analysis: dict,
) -> dict:
    return {
        "detection_id": candidate["detection_id"],
        "label": label,
        "model_label_variants": candidate["label_variants"],
        "model_confidence": candidate["Model güven puanı"],
        "confidence_threshold": analysis["threshold"],
        "bbox_xyxy_pixels": list(candidate["box"]),
        "image_width_pixels": analysis["image_width"],
        "image_height_pixels": analysis["image_height"],
        "model_id": MODEL_ID,
        "review_status": "confirmed_by_user",
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def apply_review_decisions(
    observations: list[dict],
    analysis: dict,
    review_candidates: list[dict],
    decisions: dict[str, dict],
) -> tuple[list[dict], dict[str, int]]:
    """Upsert one image-level observation, preserving its date and location."""
    image_sha256 = analysis["image_sha256"]
    observation = next(
        (item for item in observations if item.get("image_sha256") == image_sha256),
        None,
    )
    counts = {"approved": 0, "rejected": 0, "pending": 0}
    if observation is None and not any(
        decisions.get(candidate["candidate_id"], {}).get("decision") == "Onayla"
        for candidate in review_candidates
    ):
        counts["pending"] = sum(
            decisions.get(candidate["candidate_id"], {}).get("decision") == "Bekliyor"
            for candidate in review_candidates
        )
        counts["rejected"] = sum(
            decisions.get(candidate["candidate_id"], {}).get("decision") == "Reddet"
            for candidate in review_candidates
        )
        return observations, counts

    if observation is None:
        observation = {
            "observation_id": observation_id_for_image(image_sha256),
            "image_sha256": image_sha256,
            "record_type": "unclassified",
            "observation_date": None,
            "date_source": None,
            "location": None,
            "location_source": None,
            "approved_detections": [],
        }
        observations.append(observation)

    detections = {
        item["detection_id"]: item
        for item in observation.get("approved_detections", [])
    }
    for candidate in review_candidates:
        decision = decisions.get(candidate["candidate_id"], {})
        value = decision.get("decision", "Bekliyor")
        detection_id = candidate["detection_id"]
        if value == "Onayla":
            detections[detection_id] = make_approved_detection(
                candidate, decision.get("label", candidate["label_variants"][0]), analysis
            )
            counts["approved"] += 1
        elif value == "Reddet":
            detections.pop(detection_id, None)
            counts["rejected"] += 1
        else:
            counts["pending"] += 1

    observation["approved_detections"] = list(detections.values())
    observation["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    return observations, counts


def parse_coordinates(latitude_text: str, longitude_text: str) -> tuple[float, float]:
    def parse_one(value: str, name: str, minimum: float, maximum: float) -> float:
        try:
            coordinate = float(value.strip().replace(",", "."))
        except (AttributeError, ValueError) as error:
            raise ValueError(f"{name} sayısal olmalı.") from error
        if not math.isfinite(coordinate):
            raise ValueError(f"{name} sonlu bir sayı olmalı.")
        if not minimum <= coordinate <= maximum:
            raise ValueError(f"{name} {minimum} ile {maximum} arasında olmalı.")
        return coordinate

    return (
        parse_one(latitude_text, "Enlem", -90, 90),
        parse_one(longitude_text, "Boylam", -180, 180),
    )


def format_observation_popup(observation: dict) -> str:
    detections = observation.get("approved_detections", [])
    type_counts = Counter(item.get("label", "Belirtilmemiş") for item in detections)
    types_html = "<br>".join(
        f"{html.escape(label)}: {count}" for label, count in sorted(type_counts.items())
    ) or "Onaylı nesne yok"
    if observation.get("record_type") == "scenario":
        title = html.escape(observation.get("scenario_label", "Senaryo"))
        record_label = f"<b>{title}</b><br>Gerçek saha kaydı değildir"
    else:
        record_label = "<b>Gerçek gözlem</b>"
    date_value = html.escape(observation.get("observation_date") or "Tarih girilmedi")
    source_value = html.escape(observation.get("location_source") or "Kaynak belirtilmedi")
    return (
        f"{record_label}<br>Tarih: {date_value}<br>"
        f"Konum kaynağı: {source_value}<br>"
        f"Onaylı nesne sayısı: {len(detections)}<br>Türler:<br>{types_html}"
    )


def make_base_map(*, location=TRABZON_CENTER, zoom_start=11):
    """Create a keyless Esri map with OSM DE tiles underneath as fallback.

    Both layers are independent of application data. If Esri tiles are
    blocked or unavailable, the OSM DE layer remains usable without a key.
    """
    map_view = folium.Map(
        location=location,
        zoom_start=zoom_start,
        control_scale=True,
        tiles=None,
    )
    # Add fallback first so the primary Esri layer can render above it; a
    # failed primary request leaves the already available OSM layer visible.
    folium.TileLayer(
        tiles=OSM_DE_TILE_URL,
        attr=OSM_DE_ATTRIBUTION,
        name="OpenStreetMap DE (yedek)",
        overlay=False,
        control=False,
        show=True,
    ).add_to(map_view)
    folium.TileLayer(
        tiles=ESRI_TILE_URL,
        attr=ESRI_TILE_ATTRIBUTION,
        name="Esri World Street Map",
        overlay=False,
        control=False,
        show=True,
    ).add_to(map_view)
    return map_view


def make_observation_map(
    observations: list[dict],
    layer: str,
    selected_location: dict | None = None,
) -> folium.Map:
    map_view = make_base_map()
    if layer in ("Tümü", "Gerçek gözlemler"):
        for observation in observations:
            location = observation.get("location")
            if (
                observation.get("record_type") != "real"
                or not isinstance(location, dict)
                or not location
            ):
                continue
            latitude, longitude = parse_coordinates(
                str(location.get("latitude")), str(location.get("longitude"))
            )
            if not observation.get("approved_detections"):
                continue
            folium.Marker(
                [latitude, longitude],
                tooltip="Gerçek gözlem",
                popup=folium.Popup(format_observation_popup(observation), max_width=320),
                icon=folium.Icon(color="green", icon="info-sign"),
            ).add_to(map_view)

    if layer in ("Tümü", "Senaryo noktaları"):
        for scenario in SCENARIO_DEMO_RECORDS:
            location = scenario["location"]
            folium.Marker(
                [location["latitude"], location["longitude"]],
                tooltip=scenario["scenario_label"],
                popup=folium.Popup(format_observation_popup(scenario), max_width=320),
                icon=folium.Icon(color="orange", icon="info-sign"),
            ).add_to(map_view)
        for observation in observations:
            location = observation.get("location")
            if (
                observation.get("record_type") != "scenario"
                or not isinstance(location, dict)
                or not location
                or not observation.get("approved_detections")
            ):
                continue
            latitude, longitude = parse_coordinates(
                str(location.get("latitude")), str(location.get("longitude"))
            )
            folium.Marker(
                [latitude, longitude],
                tooltip="Kaydedilmiş senaryo",
                popup=folium.Popup(format_observation_popup(observation), max_width=320),
                icon=folium.Icon(color="orange", icon="info-sign"),
            ).add_to(map_view)

    if selected_location is not None:
        latitude, longitude = parse_coordinates(
            str(selected_location.get("latitude")),
            str(selected_location.get("longitude")),
        )
        folium.Marker(
            [latitude, longitude],
            tooltip="Ge\u00e7ici konum se\u00e7imi",
            popup=folium.Popup(
                "<b>Ge\u00e7ici konum se\u00e7imi</b><br>Hen\u00fcz kaydedilmedi.<br>"
                f"Enlem: {latitude:.6f}<br>Boylam: {longitude:.6f}",
                max_width=280,
            ),
            icon=folium.Icon(color="red", icon="map-marker"),
        ).add_to(map_view)
    return map_view


def route_comparison_bounds(comparison: dict) -> list[list[float]]:
    points = [point for prefix in ('current', 'recommended')
              for leg in comparison[f'{prefix}_legs'] for point in leg['coordinates']]
    return [[min(p[0] for p in points), min(p[1] for p in points)],
            [max(p[0] for p in points), max(p[1] for p in points)]]


def make_route_map(
    route: dict, stops_by_id: dict[str, dict], title: str, bounds: list | None = None
) -> folium.Map:
    """Render configured maritime polylines for one route comparison result."""
    map_view = make_base_map()
    edge_passes = repeated_edge_passes(route["legs"])
    for leg_number, (leg, (edge_total, edge_pass)) in enumerate(
        zip(route["legs"], edge_passes), start=1
    ):
        repeated = edge_total > 1
        polyline = folium.PolyLine(
            leg["coordinates"],
            color="#b23a48" if repeated and edge_pass > 1 else "#087f8c",
            weight=5,
            opacity=0.9,
            dash_array="8, 7" if repeated and edge_pass > 1 else None,
            tooltip=(
                f"Bacak {leg_number}: {leg['distance_km']:.2f} km"
                + (
                    f" · ayn\u0131 ba\u011flant\u0131 {edge_pass}. kez ge\u00e7iliyor"
                    if repeated
                    else ""
                )
            ),
        ).add_to(map_view)
        PolyLineTextPath(
            polyline,
            "\u25b6",
            repeat=False,
            center=True,
            offset=0,
            attributes={
                "fill": "#b23a48" if repeated and edge_pass > 1 else "#064f59",
                "font-weight": "bold",
                "font-size": "12",
            },
        ).add_to(map_view)

    start_id = route["nodes"][0]
    end_id = route["nodes"][-1]
    route_nodes = {**DEMO_VESSEL_NODES, **DEMO_SCENARIO_NODES, **stops_by_id}
    start = route_nodes[start_id]
    end = route_nodes[end_id]
    folium.Marker(
        [start["latitude"], start["longitude"]],
        tooltip="Başlangıç",
        popup=html.escape(start.get("label", start_id)),
        icon=folium.Icon(color="blue", icon="play"),
    ).add_to(map_view)

    for visit_number, observation_id in enumerate(route["visits"], start=1):
        stop = route_nodes[observation_id]
        folium.Marker(
            [stop["latitude"], stop["longitude"]],
            tooltip=f"Ziyaret {visit_number}: {html.escape(stop['label'])}",
            popup=html.escape(stop["label"]),
            icon=folium.DivIcon(
                html=(
                    '<div style="background:#fbbf24;color:#0b1326;border-radius:50%;'
                    'width:32px;height:32px;text-align:center;line-height:28px;'
                    'border:2px solid white;box-shadow:0 2px 6px #0b1326;'
                    f'font:800 17px/28px sans-serif">{visit_number}</div>'
                ),
                icon_size=(32, 32), icon_anchor=(16, 16),
            ),
        ).add_to(map_view)
    folium.Marker(
        [end["latitude"], end["longitude"]],
        tooltip="Dönüş",
        popup=html.escape(end.get("label", end_id)),
        icon=folium.Icon(color="darkblue", icon="home"),
    ).add_to(map_view)
    map_view.get_root().title = title
    if bounds is None:
        points = [p for leg in route['legs'] for p in leg['coordinates']]
        bounds = [[min(p[0] for p in points), min(p[1] for p in points)],
                  [max(p[0] for p in points), max(p[1] for p in points)]]
    map_view.fit_bounds(bounds, padding=(40, 40), max_zoom=13)
    return map_view


def run_route_with_progress(task):
    """Run route work off the Streamlit script thread and keep elapsed time visible."""
    updates: Queue[str] = Queue()
    status = st.status("Rota hesaplan\u0131yor", expanded=True)
    elapsed_display = st.empty()
    started_at = monotonic()
    phase = "\u0130\u015flem ba\u015flat\u0131l\u0131yor"
    last_refresh = 0.0

    def refresh_progress(force: bool = False) -> None:
        nonlocal last_refresh
        elapsed = monotonic() - started_at
        if force or elapsed - last_refresh >= 0.75:
            status.update(
                label=f"Rota hesaplan\u0131yor - {phase}",
                state="running",
                expanded=True,
            )
            elapsed_display.markdown(
                f"**A\u015fama:** {phase}  \n**Ge\u00e7en s\u00fcre:** {elapsed:.2f} sn"
            )
            last_refresh = elapsed

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="aqualitter-route") as executor:
        future = executor.submit(task, updates)
        while not future.done():
            try:
                phase = updates.get(timeout=0.2)
                refresh_progress(force=True)
            except Empty:
                refresh_progress()
        while True:
            try:
                phase = updates.get_nowait()
            except Empty:
                break
        try:
            result = future.result()
        except Exception as error:
            elapsed = monotonic() - started_at
            elapsed_display.markdown(
                f"**A\u015fama:** Hata ({phase})  \n**Ge\u00e7en s\u00fcre:** {elapsed:.2f} sn"
            )
            status.update(
                label=f"Rota hesaplanamad\u0131 - {phase}",
                state="error",
                expanded=True,
            )
            return None, error, status

    elapsed = monotonic() - started_at
    elapsed_display.markdown(
        f"**A\u015fama:** Tamamland\u0131  \n**Ge\u00e7en s\u00fcre:** {elapsed:.2f} sn"
    )
    status.update(
        label="Rota hesaplama tamamland\u0131",
        state="complete",
        expanded=False,
    )
    return result, None, status


def render_fuel_comparison(route: dict) -> None:
    """Recompute from this rerun's successful route; never persist estimated results."""
    st.subheader("Tahmini yakıt ve egzoz CO₂ karşılaştırması")
    consumption = st.number_input(
        "Tekne tüketimi (L/deniz mili)",
        min_value=0.0,
        value=None,
        step=0.1,
        format="%.4f",
        placeholder="Tekne tüketimini girin",
        key="marine_fuel_consumption",
        help="Sıfırdan büyük bir değer girin. Hazır tüketim varsayımı kullanılmaz.",
    )
    st.caption(
        "Tahmin iki rotada aynı sabit L/deniz mili tüketimini kullanır. "
        "Hız, akıntı, yük ve atık toplama sırasında tüketim modellenmez."
    )
    with st.expander("Metodoloji: tahmini yakıt ve egzoz CO₂"):
        st.markdown(
            "Yakıt (L) = mesafe (deniz mili) × tüketim (L/deniz mili)  \n"
            "CO₂ (kg) = yakıt (L) × emisyon katsayısı (kg CO₂/L)  \n"
            "1 deniz mili = 1,852 km. Hesap tam sayısal hassasiyetle yapılır; "
            "yalnızca gösterilen sonuçlar yuvarlanır.\n\n"
            f"Kaynak: [US EPA, GHG Emission Factors Hub 2025]({EPA_SOURCE_URL}#page=2), "
            f"{EPA_SOURCE_DATE}, Tablo 2 — Mobile Combustion CO₂, Diesel Fuel: "
            "10,21 kg CO₂/ABD galonu. "
            f"[NIST Handbook 130 (2025), VI §2.6.1]({NIST_SOURCE_URL}) "
            "dönüşümüyle 1 ABD galonu = 3,785411784 L; "
            f"kullanılan katsayı ≈ **{DIESEL_KG_CO2_PER_LITER:.6f} kg CO₂/L** "
            "(hesapta yuvarlanmamış bölüm kullanılır).\n\n"
            "Kapsam: petrol kökenli dizelin yanması sonucu doğrudan egzoz CO₂'si. "
            "Bu genel yakıt katsayısı tekneye özgü ölçüm değildir. Yakıt üretimi/taşınması "
            "ve yaşam döngüsü emisyonları ile CH₄ ve N₂O dahil değildir; sonuç CO₂e değildir. "
            "Tüketim kullanıcı girdisidir; ölçümünüz veya belirlediğiniz senaryo varsayımı olabilir."
        )
    if consumption is None:
        st.info("Tahmini yakıt ve CO₂ için tekne tüketimini girin.")
        return
    try:
        estimates = compare_fuel_co2(
            route["current_km"], route["recommended_km"], consumption
        )
    except ValueError as error:
        st.error(f"Yakıt/CO₂ tahmini hesaplanamadı: {error}")
        return
    columns = st.columns(3)
    for column, key, label in zip(
        columns, ("current", "recommended", "difference"), ("Mevcut", "Önerilen", "Fark")
    ):
        sign = "+" if key == "difference" else ""
        column.metric(f"{label} tahmini yakıt", f"{estimates[key]['fuel_l']:{sign}.2f} L")
        column.metric(f"{label} tahmini egzoz CO₂", f"{estimates[key]['co2_kg']:{sign}.2f} kg CO₂")
    st.caption("Fark = mevcut − önerilen. Pozitif değer daha kısa rotanın tahmini azalmasıdır.")


def coordinates_from_map_result(map_result: dict | None) -> tuple[float, float] | None:
    if not isinstance(map_result, dict):
        return None
    click = map_result.get("last_clicked")
    if not isinstance(click, dict):
        return None
    return parse_coordinates(str(click.get("lat")), str(click.get("lng")))


def update_map_selection(session_state, observation_id: str, map_result: dict | None) -> bool:
    """Store a changed map click for the selected observation; return whether it moved."""
    coordinate = coordinates_from_map_result(map_result)
    if coordinate is None:
        return False
    key = f"map_click_{observation_id}"
    new_location = {"latitude": coordinate[0], "longitude": coordinate[1]}
    previous = session_state.get(key)
    if (
        previous is not None
        and previous.get("latitude") == new_location["latitude"]
        and previous.get("longitude") == new_location["longitude"]
    ):
        return False
    session_state[key] = new_location
    return True


def validate_observation_date(date_text: str) -> str:
    try:
        return date.fromisoformat(date_text.strip()).isoformat()
    except (AttributeError, ValueError) as error:
        raise ValueError("Gözlem tarihi YYYY-AA-GG biçiminde girilmeli.") from error


def update_observation_location(
    observations: list[dict],
    observation_id: str,
    record_type: str,
    date_text: str,
    latitude: float,
    longitude: float,
    location_source: str,
) -> list[dict]:
    if record_type not in ("real", "scenario"):
        raise ValueError("Kayıt türünü Gerçek gözlem veya Senaryo olarak seçin.")
    if location_source not in ("map_click", "manual_coordinates"):
        raise ValueError("Konum kaynağı geçersiz.")
    observation_date = validate_observation_date(date_text)
    latitude, longitude = parse_coordinates(str(latitude), str(longitude))
    observation = next(
        (item for item in observations if item.get("observation_id") == observation_id),
        None,
    )
    if observation is None:
        raise ValueError("Güncellenecek gözlem kaydı bulunamadı.")
    observation.update(
        {
            "record_type": record_type,
            "observation_date": observation_date,
            "date_source": "user_entered",
            "location": {"latitude": latitude, "longitude": longitude},
            "location_source": location_source,
            "location_status": "located",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    return observations


def draw_detections(image: Image.Image, rows: list[dict]) -> Image.Image:
    result = image.copy().convert("RGB")
    draw = ImageDraw.Draw(result)
    colors = ["#14a86f", "#1877c9", "#d67b00", "#9b59b6", "#d1495b"]
    width, height = result.size

    for index, row in enumerate(rows):
        x1, y1, x2, y2 = row["box"]
        x1 = max(0, min(width - 1, x1))
        x2 = max(0, min(width - 1, x2))
        y1 = max(0, min(height - 1, y1))
        y2 = max(0, min(height - 1, y2))
        color = colors[index % len(colors)]
        draw.rectangle((x1, y1, x2, y2), outline=color, width=max(3, width // 400))
        label = f"{row['İfade (İngilizce)']} | {row['Model güven puanı']:.0%}"
        text_box = draw.textbbox((0, 0), label)
        label_width = text_box[2] - text_box[0]
        label_height = text_box[3] - text_box[1]
        label_top = max(0, y1 - label_height - 8)
        draw.rectangle(
            (x1, label_top, min(width - 1, x1 + label_width + 10), y1),
            fill=color,
        )
        draw.text((x1 + 5, label_top + 2), label, fill="white")
    return result


def observation_table_rows(observations: list[dict]) -> list[dict]:
    rows = []
    for observation in observations:
        detections = observation.get("approved_detections", [])
        types = Counter(item.get("label", "Belirtilmemiş") for item in detections)
        location = observation.get("location") or {}
        has_location = "latitude" in location and "longitude" in location
        rows.append(
            {
                "Tür": {
                    "real": "Gerçek",
                    "scenario": "Senaryo",
                    "unclassified": "Sınıflandırılmadı",
                }.get(observation.get("record_type"), "Bilinmiyor"),
                "Tarih": observation.get("observation_date") or "Bekliyor",
                "Konum": (
                    f"{location['latitude']:.5f}, {location['longitude']:.5f}"
                    if has_location
                    else "Bekliyor"
                ),
                "Konum kaynağı": observation.get("location_source") or "Belirtilmedi",
                "Onaylı nesne sayısı": len(detections),
                "Türler": ", ".join(
                    f"{label}: {count}" for label, count in sorted(types.items())
                ) or "Yok",
                "Gözlem kimliği": observation.get("observation_id", ""),
            }
        )
    return rows


def render_analysis_page():
    st.caption("Fotoğrafı yükleyin, gerçek yerel modelle analiz edin ve adayları inceleyin.")
    context_badge("Genel nesne modeli · Kullanıcı doğrulaması gerekli")
    with st.expander("Model kapsamı ve yerel kurulum ayrıntıları"):
        st.info(
            "Kullanılan Grounding DINO Tiny genel amaçlı, açık kelimeli bir nesne modelidir; "
            "atık veya kıyı fotoğraflarına özel eğitilmemiştir. Sonuçlar yalnızca "
            "kullanıcının doğrulayacağı atık adaylarıdır. Model güven puanı doğruluk garantisi değildir."
        )
        st.caption(
            "Model ve tüm işlemci/tokenizer dosyaları models/grounding-dino-tiny klasöründe "
            "bulunmalıdır. Resmî indirme yaklaşık 689 MB ağırlık içerir; komut README'dedir."
        )

    st.session_state.setdefault("analysis_runs", {})

    upload_key = f"analysis_upload_{st.session_state.get('photo_upload_generation', 0)}"
    uploaded = st.file_uploader(
        "Bir kıyı fotoğrafı seçin", type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=False, key=upload_key,
        on_change=capture_upload, args=(upload_key,),
    )
    if uploaded is not None:
        st.session_state['active_photo'] = {'name': uploaded.name, 'bytes': uploaded.getvalue()}
    photo = st.session_state.get('active_photo')
    if photo is not None:
        st.caption(f"Seçili fotoğraf: {photo['name']} · yalnızca bu oturumda tutulur")
        st.button("Fotoğrafı kaldır", key='clear_active_photo', on_click=clear_photo)
    st.session_state.setdefault('analysis_threshold', .30)
    threshold = st.slider("En düşük model güven puanı", min_value=.10, max_value=.80,
                          step=.05, key='analysis_threshold')

    image = None
    raw_image = None
    image_sha256 = None
    if photo is not None:
        try:
            raw_image = photo["bytes"]
            image_sha256 = hashlib.sha256(raw_image).hexdigest()
            image = ImageOps.exif_transpose(Image.open(BytesIO(raw_image))).convert("RGB")
            st.image(image, caption="Yüklenen görüntü", width="stretch")
        except Exception as error:
            st.error(
                "Görüntü dosyası okunamadı veya desteklenen bir görüntü biçimi değil. "
                f"Dosya okuma hatası ({type(error).__name__}): {error}"
            )

    if photo is not None and image is not None:
        analysis_hash_input = f"{image_sha256}|{threshold:.2f}|{PROMPT}"
        analysis_id = hashlib.sha256(analysis_hash_input.encode("utf-8")).hexdigest()

        if st.button("Analizi başlat", type="primary", width="stretch"):
            st.session_state.analysis_runs.pop(analysis_id, None)
            try:
                with st.spinner("Yerel model yükleniyor…"):
                    processor, model, device = load_model()
            except ModelLoadError as error:
                st.error(f"Model yükleme hatası. Analiz yapılmadı; tespit sonucu yok. {error}")
            except Exception as error:
                st.error(
                    "Model yükleme hatası. Analiz yapılmadı; tespit sonucu yok. "
                    f"{type(error).__name__}: {error}"
                )
            else:
                try:
                    with st.spinner("Görüntü analiz ediliyor…"):
                        raw_candidates = run_inference(
                            image, threshold, processor, model, device
                        )
                except Exception as error:
                    st.error(
                        "Inference hatası: model yüklendi ancak görüntü analizi "
                        f"tamamlanamadı. Tespit sonucu yok. {type(error).__name__}: {error}"
                    )
                else:
                    review_candidates = group_duplicate_candidates(raw_candidates)
                    for index, candidate in enumerate(review_candidates):
                        candidate["detection_id"] = detection_id_for_box(
                            image_sha256, candidate["box"]
                        )
                        candidate["candidate_id"] = hashlib.sha256(
                            f"{analysis_id}:{index}:{candidate['box']}".encode("utf-8")
                        ).hexdigest()[:20]

                    st.session_state.analysis_runs[analysis_id] = {
                        "image_sha256": image_sha256,
                        "image_width": image.width,
                        "image_height": image.height,
                        "threshold": threshold,
                        "raw_candidates": raw_candidates,
                        "review_candidates": review_candidates,
                    }

        analysis = st.session_state.analysis_runs.get(analysis_id)
        if analysis is not None:
            raw_candidates = analysis["raw_candidates"]
            review_candidates = analysis["review_candidates"]
            if not raw_candidates:
                st.info(NO_DETECTIONS)
            else:
                with st.expander("Ham model adayları ve kutu ayrıntıları"):
                    st.subheader(f"Ham model adayları ({len(raw_candidates)})")
                    st.caption(
                        "Aşağıdaki tablo modelin ham ifadelerini korur. Yalnızca aynı piksel "
                        "koordinatlarına sahip kutular incelemede gruplanır; farklı koordinatlı "
                        "adaylar ayrı kalır ve ham satırlar silinmez."
                    )
                    group_for_raw = {}
                    for group_number, candidate in enumerate(review_candidates, start=1):
                        for raw_index in candidate["raw_indices"]:
                            group_for_raw[raw_index] = (group_number, candidate["raw_count"])

                    st.dataframe(
                        [
                            {
                                "Ham sıra": raw_index + 1,
                                "Modelin ham ifadesi": candidate["Modelin ham ifadesi"],
                                "Model güven puanı": f"{candidate['Model güven puanı']:.1%}",
                                "Kutu (x1, y1, x2, y2) px": candidate[
                                    "Kutu (x1, y1, x2, y2) px"
                                ],
                                "Geometri grubu": (
                                    f"Grup {group_for_raw[raw_index][0]} "
                                    f"({group_for_raw[raw_index][1]} ham aday)"
                                    if group_for_raw[raw_index][1] > 1
                                    else "Tekil kutu"
                                ),
                            }
                            for raw_index, candidate in enumerate(raw_candidates)
                        ],
                        width="stretch",
                        hide_index=True,
                    )

                st.subheader("İnceleme adayları")
                st.caption(
                    "Yalnızca aynı piksel koordinatlarına sahip kutular gruplanır. Farklı "
                    "koordinatlı adaylar ayrı kalır. Her grubun ham ifadeleri arasından etiketi seçin; sonra Onayla "
                    "veya Reddet kararını verin. Bekleyen adaylar kaydedilmez."
                )
                st.image(
                    draw_detections(image, review_candidates),
                    caption="İnceleme için gruplandırılmış aday kutuları",
                    width="stretch",
                )

                try:
                    saved_observations = load_observations()
                    saved_for_image = next(
                        (
                            item
                            for item in saved_observations
                            if item.get("image_sha256") == analysis["image_sha256"]
                        ),
                        None,
                    )
                    saved_detections = {
                        item["detection_id"]: item
                        for item in (saved_for_image or {}).get("approved_detections", [])
                    }
                except Exception as error:
                    saved_detections = {}
                    st.error(
                        "Önceki gözlem kayıtları okunamadı; inceleme sonucu etkilenmedi. "
                        f"{type(error).__name__}: {error}"
                    )

                for index, candidate in enumerate(review_candidates, start=1):
                    candidate_id = candidate["candidate_id"]
                    label_key = f"review_label_{candidate_id}"
                    decision_key = f"review_decision_{candidate_id}"
                    previous_detection = saved_detections.get(candidate["detection_id"])
                    if label_key not in st.session_state:
                        previous_label = (previous_detection or {}).get("label")
                        st.session_state[label_key] = (
                            previous_label
                            if previous_label in candidate["label_variants"]
                            else candidate["label_variants"][0]
                        )
                    if decision_key not in st.session_state:
                        st.session_state[decision_key] = (
                            "Onayla" if previous_detection else "Bekliyor"
                        )

                    with st.container(border=True):
                        st.markdown(
                            f"**Aday {index}** · model puanı "
                            f"{candidate['Model güven puanı']:.1%} · "
                            f"kutu {candidate['Kutu (x1, y1, x2, y2) px']}"
                        )
                        st.caption(
                            f"{candidate['raw_count']} ham model ifadesi bu aynı kutuda gruplandı."
                        )
                        st.selectbox(
                            "Onaylanacak model ifadesi",
                            candidate["label_variants"],
                            key=label_key,
                        )
                        st.radio(
                            "İnceleme kararı",
                            ["Bekliyor", "Onayla", "Reddet"],
                            key=decision_key,
                            horizontal=True,
                        )

                if st.button(
                    "İnceleme kararlarını kaydet",
                    key=f"save_review_{analysis_id}",
                    width="stretch",
                ):
                    try:
                        observations = load_observations()
                        decisions = {}
                        for candidate in review_candidates:
                            candidate_id = candidate["candidate_id"]
                            decisions[candidate_id] = {
                                "decision": st.session_state[
                                    f"review_decision_{candidate_id}"
                                ],
                                "label": st.session_state[f"review_label_{candidate_id}"],
                            }
                        observations, counts = apply_review_decisions(
                            observations, analysis, review_candidates, decisions
                        )
                        save_observations(observations)
                        st.success(
                            f"Gözlem güncellendi: {counts['approved']} onay, "
                            f"{counts['rejected']} ret, {counts['pending']} bekleyen."
                        )
                    except Exception as error:
                        st.error(
                            "Gözlem kaydı okunamadı veya güncellenemedi. "
                            f"Model sonucu değişmedi. {type(error).__name__}: {error}"
                        )


def render_observation_page():
    with st.expander("Kullanıcı kayıtları ve JSON dışa aktarma"):
        st.subheader("Kullanıcı tarafından onaylanan gözlemler")
        try:
            observations = load_observations()
        except Exception as error:
            observations = []
            st.error(
                "Gözlem kayıt dosyası okunamadı; yeni model adayları değişmedi. "
                f"{type(error).__name__}: {error}"
            )
        else:
            if observations:
                st.dataframe(
                    observation_table_rows(observations),
                    width="stretch",
                    hide_index=True,
                )
                st.download_button(
                    "Gözlem kayıtlarını JSON indir",
                    data=json.dumps(
                        {"schema_version": 2, "observations": observations},
                        ensure_ascii=False,
                        indent=2,
                    ).encode("utf-8"),
                    file_name="aqualitter_observations.json",
                    mime="application/json",
                    width="stretch",
                )
            else:
                st.info("Henüz kullanıcı tarafından onaylanmış fotoğraf gözlemi yok.")

    st.subheader("Trabzon kıyıları · kirlilik gözlem haritası")
    st.caption(
        "Harita başlangıç görünümü Trabzon kıyılarıdır. Yeşil noktalar konumu kullanıcıca "
        "belirtilmiş gerçek gözlemleri, turuncu noktalar açıkça etiketlenmiş senaryoları gösterir."
    )
    st.warning(
        "Senaryo noktaları ve örnek tür sayıları temsili veridir; gerçek saha bulgusu değildir. "
        "Nesne sayısı kg veya fiziksel kirlilik yoğunluğu anlamına gelmez."
    )

    layer = st.radio(
        "Harita katmanı",
        ["Tümü", "Gerçek gözlemler", "Senaryo noktaları"],
        horizontal=True,
        key="observation_map_layer",
    )

    observation_by_id = {
        item["observation_id"]: item
        for item in observations
        if item.get("observation_id")
    }
    observation_ids = list(observation_by_id)
    selected_observation_id = None
    selected_observation = None
    if observation_ids:
        option_labels = {
            observation_id: (
                f"{observation_by_id[observation_id].get('record_type', 'unclassified')} · "
                f"{len(observation_by_id[observation_id].get('approved_detections', []))} onaylı nesne · "
                f"{observation_by_id[observation_id].get('image_sha256', '')[:10]}"
            )
            for observation_id in observation_ids
        }
        if st.session_state.get("map_edit_observation_id") not in observation_ids:
            st.session_state["map_edit_observation_id"] = observation_ids[0]
        selected_observation_id = st.selectbox(
            "Konumu ve tarihi düzenlenecek fotoğraf gözlemi",
            observation_ids,
            format_func=lambda value: option_labels[value],
            key="map_edit_observation_id",
        )
        selected_observation = observation_by_id[selected_observation_id]
    else:
        st.info(
            "Haritaya gerçek gözlem eklemek için önce fotoğrafı analiz edip en az bir adayı onaylayın."
        )

    selection_key = f"map_click_{selected_observation_id}" if selected_observation_id else None
    selected_map_location = (
        st.session_state.get(selection_key) if selection_key is not None else None
    )

    try:
        map_object = make_observation_map(
            observations,
            layer,
            selected_location=selected_map_location,
        )
        map_component_key = f"observation_map_{layer}_{selected_observation_id or 'none'}"
        map_result = st_folium(
            map_object,
            key=map_component_key,
            height=580,
            width=None,
            use_container_width=True,
            returned_objects=["last_clicked"],
        )
    except Exception as error:
        map_result = None
        st.error(
            "Harita görüntülenemedi. Harita bileşeni veya çevrim içi harita döşemeleri "
            f"erişilemiyor olabilir. {type(error).__name__}: {error}"
        )

    if selected_observation_id and map_result:
        try:
            if update_map_selection(st.session_state, selected_observation_id, map_result):
                st.rerun()
        except ValueError as error:
            st.error(f"Haritadan gecersiz koordinat geldi: {error}")

    if selected_observation_id:
        selected_map_location = st.session_state.get(selection_key)
        if selected_map_location:
            st.success(
                "G\u00e7ici harita se\u00e7imi (hen\u00fcz kaydedilmedi): "
                f"enlem {selected_map_location['latitude']:.6f}, "
                f"boylam {selected_map_location['longitude']:.6f}. "
                "K\u0131rm\u0131z\u0131 i\u015faret\u00e7i bu konumu g\u00f6sterir."
            )
        else:
            st.caption(
                "Haritaya t\u0131klay\u0131n; ge\u00e7ici i\u015faret\u00e7i ve se\u00e7ilen "
                "enlem-boylam burada g\u00f6r\u00fcnecek."
            )

    if selected_observation is not None:
        st.markdown("#### Seçili gözlemin konumu ve tarihi")
        stored_location = selected_observation.get("location") or {}
        record_type_labels = {
            "unclassified": "Belirsiz · seçim gerekli",
            "real": "Gerçek gözlem",
            "scenario": "Senaryo",
        }
        type_options = list(record_type_labels.values())
        current_type_label = record_type_labels.get(
            selected_observation.get("record_type"), type_options[0]
        )
        type_key = f"record_type_{selected_observation_id}"
        if type_key not in st.session_state:
            st.session_state[type_key] = current_type_label
        selected_type_label = st.selectbox(
            "Kayıt türü",
            type_options,
            key=type_key,
        )

        date_key = f"observation_date_{selected_observation_id}"
        if date_key not in st.session_state:
            st.session_state[date_key] = selected_observation.get("observation_date") or ""
        observation_date = st.text_input(
            "Gözlem tarihi (YYYY-AA-GG)",
            key=date_key,
            placeholder="Örn. 2026-10-30",
            help="Fotoğrafın EXIF bilgisinden tarih çıkarılmaz; doğru gözlem tarihini siz girin.",
        )

        method_options = ["Haritada seç", "Enlem-boylam gir"]
        current_method = (
            "Enlem-boylam gir"
            if selected_observation.get("location_source") == "manual_coordinates"
            else "Haritada seç"
        )
        method_key = f"location_method_{selected_observation_id}"
        if method_key not in st.session_state:
            st.session_state[method_key] = current_method
        location_method = st.radio(
            "Konumu belirleme yöntemi",
            method_options,
            horizontal=True,
            key=method_key,
        )

        latitude_text = ""
        longitude_text = ""
        if location_method == "Haritada se\u00e7":
            selected_map_location = st.session_state.get(selection_key)
            if (
                not selected_map_location
                and stored_location
                and selected_observation.get("location_source") == "map_click"
            ):
                st.info(
                    "Kay\u0131tl\u0131 harita koordinat\u0131: "
                    f"{stored_location['latitude']:.6f}, {stored_location['longitude']:.6f}"
                )
        else:
            latitude_key = f"latitude_{selected_observation_id}"
            longitude_key = f"longitude_{selected_observation_id}"
            if latitude_key not in st.session_state:
                st.session_state[latitude_key] = (
                    str(stored_location.get("latitude", "")) if stored_location else ""
                )
            if longitude_key not in st.session_state:
                st.session_state[longitude_key] = (
                    str(stored_location.get("longitude", "")) if stored_location else ""
                )
            latitude_text = st.text_input("Enlem", key=latitude_key, placeholder="41.0053")
            longitude_text = st.text_input("Boylam", key=longitude_key, placeholder="39.7267")

        if st.button(
            "Gözlem konumunu ve tarihini kaydet",
            key=f"save_location_{selected_observation_id}",
            width="stretch",
        ):
            try:
                if selected_type_label == "Gerçek gözlem":
                    record_type = "real"
                elif selected_type_label == "Senaryo":
                    record_type = "scenario"
                else:
                    raise ValueError("Kayıt türünü Gerçek gözlem veya Senaryo olarak seçin.")

                if location_method == "Haritada seç":
                    selected_map_location = st.session_state.get(
                        f"map_click_{selected_observation_id}"
                    )
                    if (
                        selected_map_location is None
                        and selected_observation.get("location_source") == "map_click"
                    ):
                        selected_map_location = stored_location
                    if not selected_map_location:
                        raise ValueError("Haritada bir noktaya tıklayarak konum seçin.")
                    latitude, longitude = parse_coordinates(
                        str(selected_map_location.get("latitude")),
                        str(selected_map_location.get("longitude")),
                    )
                    location_source = "map_click"
                else:
                    latitude, longitude = parse_coordinates(latitude_text, longitude_text)
                    location_source = "manual_coordinates"

                updated_observations = update_observation_location(
                    load_observations(),
                    selected_observation_id,
                    record_type,
                    observation_date,
                    latitude,
                    longitude,
                    location_source,
                )
                save_observations(updated_observations)
                if location_method == "Haritada se\u00e7":
                    st.session_state.pop(selection_key, None)
                st.success("Gözlem kaydı güncellendi; haritadaki nokta yenilendi.")
                st.rerun()
            except Exception as error:
                st.error(
                    "Gözlem konumu kaydedilmedi. Tarih ve koordinatları kontrol edin. "
                    f"{type(error).__name__}: {error}"
                )

    st.caption(
        "Kayıtlar data/confirmed_observations.json içinde tutulur (Git dışında). "
        "Gözlem tarihi ve konumu kullanıcı girdisidir; görüntü pikselleri coğrafi koordinat "
        "sayılmaz. Onaylı nesne sayısı fiziksel yoğunluk veya ağırlık ölçüsü değildir."
    )


def render_route_page():
    st.session_state.pop("route_snapshot", None)
    st.caption("Aynı başlangıç, dönüş ve ziyaretlerle mevcut ve önerilen sırayı karşılaştırın.")
    with st.expander("Kara denetimi, kıyı tamponu ve veri sınırları"):
        st.warning(
            "Rota geometrileri yalnizca yerel Natural Earth kara poligonu ile kontrol edilir. "
            f"Denetim kutusu: {TRABZON_BOUNDS[0]}-{TRABZON_BOUNDS[2]} N, "
            f"{TRABZON_BOUNDS[1]}-{TRABZON_BOUNDS[3]} E. "
            "10m katmani 1:10.000.000 olcekli genellestirilmis veridir; yakindaki kayalik, "
            "iskele ve kiyidaki kucuk ayrintilari kapsamayabilir. Ek olarak "
            f"{MIN_COAST_CLEARANCE_KM:.1f} km kiyidan uzaklik tamponu uygulanir. "
            "Bu kaba eleme seyir guvenligi dogrulamasi degildir; OSM yalnizca harita zemini olarak kullanilir."
        )
    route_land_mask = None
    route_land_mask_error = None
    if LAND_MASK_FILE.is_file():
        try:
            route_land_mask = load_route_land_mask(
                str(LAND_MASK_FILE),
                LAND_MASK_FILE.stat().st_mtime_ns,
                LAND_MASK_FILE.stat().st_size,
                hashlib.sha256(LAND_MASK_FILE.read_bytes()).hexdigest(),
                TRABZON_BOUNDS,
                MIN_COAST_CLEARANCE_KM,
            )
        except Exception as error:
            route_land_mask_error = f"{type(error).__name__}: {error}"
    else:
        route_land_mask_error = "dosya bulunamadi"

    if route_land_mask_error:
        st.error(
            "Kara-kesisim denetimi icin rota plani hazirlanamadi. Beklenen dosya: "
            f"{LAND_MASK_FILE}. Resmi indirme: "
            "https://naciscdn.org/naturalearth/10m/physical/ne_10m_land.zip "
            "(ZIP dosyasini data\\ne_10m_land.zip olarak kaydedin). "
            f"Ayrinti: {route_land_mask_error}"
        )


    route_record_type = st.radio(
        "Planlanacak gözlem türü",
        ["Senaryo", "Gerçek gözlemler"],
        horizontal=True,
        key="marine_route_record_type",
    )
    route_records = load_observations()
    if route_record_type == "Senaryo":
        route_candidates = list(SCENARIO_DEMO_RECORDS) + [
            item
            for item in route_records
            if item.get("record_type") == "scenario"
            and isinstance(item.get("location"), dict)
            and item.get("approved_detections")
        ]
    else:
        route_candidates = [
            item
            for item in route_records
            if item.get("record_type") == "real"
            and isinstance(item.get("location"), dict)
            and item.get("approved_detections")
        ]

    route_candidates_by_id = {
        item["observation_id"]: {
            "label": (
                f"{item.get('scenario_label', 'Senaryo')}"
                if item.get("record_type") == "scenario"
                else f"Gerçek gözlem · {item.get('observation_id', '')[:10]}"
            ),
            "latitude": (
                DEMO_SCENARIO_NODES[item["observation_id"]]["latitude"]
                if item["observation_id"] in DEMO_SCENARIO_NODES
                else float(item["location"]["latitude"])
            ),
            "longitude": (
                DEMO_SCENARIO_NODES[item["observation_id"]]["longitude"]
                if item["observation_id"] in DEMO_SCENARIO_NODES
                else float(item["location"]["longitude"])
            ),
        }
        for item in route_candidates
        if isinstance(item.get("location"), dict)
    }
    route_candidate_ids = list(route_candidates_by_id)

    if route_record_type == "Ger\u00e7ek g\u00f6zlemler" and route_candidate_ids:
        st.info(
            "Onayl\u0131 ger\u00e7ek g\u00f6zlemler se\u00e7ilebilir. Her g\u00f6zlem "
            "ve ba\u011flant\u0131 yaln\u0131zca yerel kara verisiyle kesi\u015fim "
            "ve 1 km k\u0131y\u0131 tamponu denetimini ge\u00e7erse rotaya eklenir."
        )
    elif not route_candidate_ids:
        st.info(
            "Bu türde konumu ve onaylı nesnesi olan gözlem yok. Senaryo "
            "noktaları ayrı türde tutulur."
        )

    vessel_labels = {
        key: value["label"] for key, value in DEMO_VESSEL_NODES.items()
    }
    route_start_id = st.selectbox(
        "Senaryo teknesi başlangıç noktası",
        list(vessel_labels),
        format_func=lambda value: vessel_labels[value],
        key="marine_route_start",
    )
    route_return_id = st.selectbox(
        "Dönüş noktası",
        list(vessel_labels),
        format_func=lambda value: vessel_labels[value],
        key="marine_route_return",
    )

    route_selected_ids = st.multiselect(
        "Ziyaret edilecek konumlu gözlemler",
        route_candidate_ids,
        format_func=lambda value: route_candidates_by_id[value]["label"],
        key=f"marine_route_stops_{'scenario' if route_record_type == 'Senaryo' else 'real'}",
        help="Nesne sayısı kg veya fiziksel kirlilik miktarına dönüştürülmez.",
    )

    if route_selected_ids:
        if len(route_selected_ids) > 6:
            st.error("Bu prototip en fazla 6 ziyaret noktasini siralayabilir.")
        else:
            order_options = list(permutations(route_selected_ids))
            order_key_digest = hashlib.sha1(
                (route_record_type + "|" + "|".join(route_selected_ids)).encode("utf-8")
            ).hexdigest()[:10]
            current_visit_order = st.selectbox(
                "Kullan\u0131c\u0131n\u0131n mevcut ziyaret s\u0131ras\u0131",
                order_options,
                format_func=lambda order: " \u2192 ".join(
                    route_candidates_by_id[item]["label"] for item in order
                ),
                key=f"marine_visit_order_{order_key_digest}",
            )

            def calculate_route(progress):
                if route_land_mask is None:
                    raise RouteNotAvailable(
                        "Yerel kara poligonu olmadan rota baglantilari dogrulanamaz."
                    )
                selected_route_nodes = {
                    item: route_candidates_by_id[item] for item in route_selected_ids
                }
                route_nodes = {
                    node_id: DEMO_VESSEL_NODES[node_id]
                    for node_id in dict.fromkeys((route_start_id, route_return_id))
                }
                route_nodes.update(selected_route_nodes)
                required_node_ids = [route_start_id, route_return_id, *route_selected_ids]
                # Reject invalid visits before creating and checking every pairwise corridor.
                progress.put("Seçilen noktalar kara poligonu ve kıyı tamponuna göre denetleniyor")
                for node_id in required_node_ids:
                    node = route_nodes[node_id]
                    reason = route_land_mask.validate_path(
                        [(node["latitude"], node["longitude"])]
                    )
                    if reason:
                        node_label = vessel_labels.get(
                            node_id,
                            route_candidates_by_id.get(node_id, {}).get("label", node_id),
                        )
                        raise RouteNotAvailable(
                            f"{node_label} erisilemiyor: {reason} Koordinat degistirilmedi."
                        )
                progress.put("Deniz koridorları kara ve kıyı tamponuna göre denetleniyor")
                validated_links, unavailable_links = build_land_checked_links(
                    route_nodes, route_land_mask
                )
                required_node_ids = [route_start_id, route_return_id, *route_selected_ids]
                for node_id in required_node_ids:
                    reason = unavailable_links.get(node_id)
                    if reason:
                        node_label = vessel_labels.get(
                            node_id,
                            route_candidates_by_id.get(node_id, {}).get("label", node_id),
                        )
                        raise RouteNotAvailable(
                            f"{node_label} erisilemiyor: {reason} Koordinat degistirilmedi."
                        )

                progress.put("Eri\u015filebilir ziyaret s\u0131ras\u0131 optimize ediliyor")
                optimized = compare_visit_orders(
                    route_start_id,
                    route_return_id,
                    list(current_visit_order),
                    links=validated_links,
                    unavailable=unavailable_links,
                )
                current_route = {
                    "nodes": optimized["current_nodes"],
                    "visits": optimized["current_order"],
                    "legs": optimized["current_legs"],
                }
                recommended_route = {
                    "nodes": optimized["recommended_nodes"],
                    "visits": optimized["recommended_order"],
                    "legs": optimized["recommended_legs"],
                }
                progress.put("\u0130ki rota haritas\u0131 ve y\u00f6n i\u015faretleri haz\u0131rlan\u0131yor")
                shared_bounds = route_comparison_bounds(optimized)
                current_map = make_route_map(
                    current_route, route_candidates_by_id, "Mevcut rota", shared_bounds
                )
                recommended_map = make_route_map(
                    recommended_route, route_candidates_by_id, "Onerilen rota", shared_bounds
                )
                return optimized, current_map, recommended_map

            calculation, calculation_error, route_status = run_route_with_progress(
                calculate_route
            )
            if calculation_error is not None:
                st.error(
                    f"Rota olu\u015fturulamad\u0131. {type(calculation_error).__name__}: "
                    f"{calculation_error}"
                )
            else:
                optimized, current_map, recommended_map = calculation
                order_columns = st.columns(2)
                order_columns[0].caption(
                    "Mevcut ziyaret s\u0131ras\u0131: "
                    + " \u2192 ".join(
                        route_candidates_by_id[item]["label"]
                        for item in optimized["current_order"]
                    )
                )
                order_columns[1].caption(
                    "Algoritma \u00f6nerisi: "
                    + " \u2192 ".join(
                        route_candidates_by_id[item]["label"]
                        for item in optimized["recommended_order"]
                    )
                )
                metric_columns = st.columns(3)
                metric_columns[0].metric(
                    "Mevcut s\u0131ra",
                    f"{optimized['current_km']:.2f} km",
                    f"{optimized['current_km'] / KM_PER_NAUTICAL_MILE:.2f} deniz mili",
                )
                metric_columns[1].metric(
                    "Algoritman\u0131n \u00f6nerisi",
                    f"{optimized['recommended_km']:.2f} km",
                    f"{optimized['recommended_km'] / KM_PER_NAUTICAL_MILE:.2f} deniz mili",
                )
                difference = optimized["difference_km"]
                metric_columns[2].metric(
                    "Mevcut - \u00f6nerilen mesafe",
                    f"{difference:+.2f} km",
                    f"{difference / KM_PER_NAUTICAL_MILE:+.2f} deniz mili",
                )
                if optimized["improved"]:
                    st.success(
                        "\u00d6nerilen ziyaret s\u0131ras\u0131 "
                        f"{optimized['improvement_km']:.2f} km daha k\u0131sa."
                    )
                else:
                    st.info("Mesafe iyile\u015fmesi yok; \u00f6nerilen s\u0131ra daha k\u0131sa de\u011fil.")

                st.session_state['route_snapshot'] = {
                    'optimized': optimized, 'signature': current_route_signature(),
                    'record_type': route_record_type,
                    'start_label': vessel_labels[route_start_id],
                    'return_label': vessel_labels[route_return_id],
                    'visit_labels': [route_candidates_by_id[x]['label'] for x in optimized['current_order']],
                }
                st.button("Yakıt ve CO₂ karşılaştırmasına geç", on_click=go_to,
                          args=(PAGES[4],), key='open_environment', width='stretch')

                left_map, right_map = st.columns(2)
                try:
                    with left_map:
                        st.subheader("Mevcut ziyaret s\u0131ras\u0131")
                        st_folium(
                            current_map,
                            key=f"marine_current_route_map_{current_route_signature()[:12]}",
                            height=520,
                            use_container_width=True,
                            returned_objects=[],
                        )
                    with right_map:
                        st.subheader("Algoritman\u0131n \u00f6nerisi")
                        st_folium(
                            recommended_map,
                            key=f"marine_recommended_route_map_{current_route_signature()[:12]}",
                            height=520,
                            use_container_width=True,
                            returned_objects=[],
                        )
                except Exception as error:
                    route_status.update(
                        label="Rota haritas\u0131 g\u00f6sterilemedi",
                        state="error",
                        expanded=True,
                    )
                    st.error(f"Rota haritas\u0131 g\u00f6sterilemedi: {type(error).__name__}: {error}")
                st.caption(
                    "Mesafe \u00e7izilen koridor segmentleri boyunca Haversine ile toplan\u0131r. "
                    "Nesne say\u0131s\u0131 kg veya fiziksel kirlilik yo\u011funlu\u011fu de\u011fildir."
                )


def source_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def current_route_signature():
    """Include current controls, records, land content and spatial settings."""
    kind = st.session_state.get('marine_route_record_type', 'Senaryo')
    selected = st.session_state.get(
        f"marine_route_stops_{'scenario' if kind == 'Senaryo' else 'real'}", []
    )
    order_key = hashlib.sha1((kind + '|' + '|'.join(selected)).encode()).hexdigest()[:10]
    payload = {
        'kind': kind, 'selected': selected,
        'start': st.session_state.get('marine_route_start', 'vessel-west'),
        'return': st.session_state.get('marine_route_return', 'vessel-west'),
        'order': st.session_state.get(f'marine_visit_order_{order_key}', tuple(selected)),
        'records': source_digest(CONFIRMED_FILE), 'land': source_digest(LAND_MASK_FILE),
        'bounds': TRABZON_BOUNDS, 'clearance': MIN_COAST_CLEARANCE_KM,
        'vessels': DEMO_VESSEL_NODES, 'scenarios': DEMO_SCENARIO_NODES,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def current_route_snapshot():
    snapshot = st.session_state.get('route_snapshot')
    if snapshot and snapshot['signature'] == current_route_signature():
        return snapshot
    st.session_state.pop('route_snapshot', None)
    return None


def render_environment_page():
    st.caption("Kara/kıyı denetiminden geçen rota mesafelerinden tahmini yakıt ve doğrudan egzoz CO₂ hesabı.")
    snapshot = current_route_snapshot()
    if snapshot is None:
        st.info("Henüz hesaplanmadı. Önce Temizlik Rotası bölümünde geçerli bir rota oluşturun.")
        st.button("Temizlik Rotası bölümüne geç", on_click=go_to, args=(PAGES[3],), key='effect_to_route')
        return
    context_badge(f"{snapshot['record_type']} planı · Tahmini sonuçlar")
    st.caption(f"{snapshot['start_label']} → {snapshot['return_label']}")
    with st.expander("Bu hesaba bağlı rota ve ziyaretler"):
        st.write(' → '.join(snapshot['visit_labels']))
        st.write(f"Mevcut: {snapshot['optimized']['current_km']:.2f} km · "
                 f"Önerilen: {snapshot['optimized']['recommended_km']:.2f} km")
    render_fuel_comparison(snapshot['optimized'])


def render_overview_page():
    st.caption("Fotoğraftan kullanıcı onayına, konumlu gözlemden deniz temizliği planına.")
    try:
        observations = load_observations()
    except Exception as error:
        observations = []
        st.error(f"Gözlem kayıtları okunamadı: {error}")
    snapshot = current_route_snapshot()
    estimate = None
    if snapshot is not None:
        try:
            estimate = compare_fuel_co2(
                snapshot['optimized']['current_km'], snapshot['optimized']['recommended_km'],
                st.session_state.get('marine_fuel_consumption'),
            )
        except ValueError:
            pass
    cards = st.columns(4)
    cards[0].metric("Kayıtlı fotoğraf gözlemi", str(len(observations)) if observations else "Henüz hesaplanmadı")
    approved = sum(len(x.get('approved_detections', [])) for x in observations)
    cards[1].metric("Onaylı nesne · kullanıcı kayıtları", str(approved) if observations else "Henüz hesaplanmadı")
    cards[2].metric("Önerilen rota", f"{snapshot['optimized']['recommended_km']:.2f} km" if snapshot else "Henüz hesaplanmadı")
    cards[3].metric("Tahmini CO₂ farkı", f"{estimate['difference']['co2_kg']:.2f} kg" if estimate else "Henüz hesaplanmadı")
    st.caption("Hazır temsili demo noktaları gözlem/nesne kartlarına dahil edilmez. "
               "Rota ve tahmini etki kartları son geçerli plana bağlıdır.")
    map_panel, summary_panel = st.columns([3, 1], gap='large')
    with map_panel:
        st.subheader("Trabzon kıyıları · gözlem alanı")
        st.caption("Yeşil: gerçek gözlem · Turuncu: senaryo · Konumlar kullanıcı girdisi veya açık demo verisidir.")
        try:
            st_folium(make_observation_map(observations, 'Tümü'), key='overview_observation_map',
                      height=550, use_container_width=True, returned_objects=[])
        except Exception as error:
            st.error(f"Canlı harita gösterilemedi: {error}")
    with summary_panel:
        with st.container(border=True):
            st.subheader("Gözlem özeti")
            real = [x for x in observations if x.get('record_type') == 'real']
            scenario = [x for x in observations if x.get('record_type') == 'scenario']
            st.write(f"Gerçek gözlem: **{len(real)}**")
            st.write(f"Kaydedilmiş senaryo: **{len(scenario)}**")
            st.write(f"Hazır deniz senaryosu: **{len(SCENARIO_DEMO_RECORDS)} nokta**")
            st.caption("Nesne sayısı kütle veya fiziksel kirlilik yoğunluğu değildir.")
            st.button("Gözlem Haritasını aç", key='overview_map', on_click=go_to, args=(PAGES[2],), width='stretch')
        with st.container(border=True):
            st.subheader("Temizlik planı")
            if snapshot:
                context_badge(f"{snapshot['record_type']} · {len(snapshot['visit_labels'])} ziyaret")
                st.write(f"Hesaplanan mesafe farkı: **{snapshot['optimized']['difference_km']:.2f} km**")
            else:
                st.write("Henüz hesaplanmadı")
            st.button("Temizlik Rotasını aç", key='overview_route', on_click=go_to, args=(PAGES[3],), width='stretch')
        st.button("Fotoğraf analizine başla", key='overview_analysis', on_click=go_to, args=(PAGES[1],), width='stretch')


def transfer_citizen_photo_to_analysis(photo, report_id):
    """Queue the citizen photo and navigate during the next Streamlit rerun.

    This runs as a button callback, before the page body is rebuilt, so the
    `active_page` radio widget is not mutated after it has been instantiated.
    """
    st.session_state["active_photo"] = {
        "name": f"citizen-{report_id}.jpg", "bytes": photo,
    }
    go_to(PAGES[1])


def render_citizen_reports_page():
    """Server-side review surface for anonymous citizen submissions.

    The privileged read key, when configured, stays in this Streamlit process;
    it is never put in widget state, HTML, logs, or the citizen application.
    """
    st.caption("Anonim vatandaş bildirimleri · yönetici incelemesi")
    st.info(
        "Bu liste yalnızca Supabase'ten gelen pending_review kayıtlarını gösterir. "
        "Vatandaş koordinatı otomatik olarak değiştirilmez veya denize taşınmaz."
    )
    try:
        config = load_admin_config(st.secrets)
    except CitizenAdminError as error:
        st.warning(str(error))
        st.caption("Gerekli ayar: .streamlit/secrets.toml içinde [supabase] altında url ve "
                   "SUPABASE_SERVICE_ROLE_KEY. Anahtar yalnızca sunucuda okunur.")
        return

    if st.button("Pending bildirimleri yenile", key="citizen_refresh"):
        st.rerun()
    try:
        reports = fetch_pending_reports(config)
    except CitizenAdminError as error:
        st.error(str(error))
        return
    if not reports:
        st.success("İnceleme bekleyen vatandaş bildirimi bulunmuyor.")
        return

    st.write(f"İnceleme bekleyen kayıt: **{len(reports)}**")
    points = []
    for report in reports:
        points.append((report["latitude"], report["longitude"], report["id"]))
    map_obj = make_base_map()
    for lat, lon, report_id in points:
        folium.Marker([lat, lon], tooltip=f"Vatandaş bildirimi · {report_id[:8]}").add_to(map_obj)
    try:
        st_folium(map_obj, key="citizen_reports_map", height=430, use_container_width=True, returned_objects=[])
    except Exception as error:
        st.warning(f"Vatandaş bildirim haritası gösterilemedi; kayıt ayrıntıları kullanılabilir: {type(error).__name__}")

    for index, report in enumerate(reports):
        title = f"{report['captured_at']} · {report['location_source']} · {report['status']}"
        with st.expander(title, expanded=index == 0):
            left, right = st.columns([1, 2], gap="large")
            photo = None
            with left:
                try:
                    photo = fetch_photo(config, report["photo_path"])
                    st.image(photo, caption="Vatandaş fotoğrafı", width="stretch")
                    st.button(
                        "Görüntü analizine aktar",
                        key=f"citizen_analyze_{report['id']}",
                        on_click=transfer_citizen_photo_to_analysis,
                        args=(photo, report["id"]),
                    )
                except CitizenAdminError as error:
                    st.warning(str(error))
            with right:
                st.write(f"**Kayıt:** `{report['id']}`")
                st.write(f"**Konum:** {report['latitude']:.6f}, {report['longitude']:.6f}")
                accuracy = "Bilinmiyor (manuel seçim)" if report["accuracy_m"] is None else f"{report['accuracy_m']:.1f} m"
                st.write(f"**GPS doğruluğu:** {accuracy} · garanti değildir")
                st.write(f"**Konum kaynağı:** {report['location_source']}")
                st.write(f"**Alınan zaman:** {report['captured_at']}")
                st.write(f"**Durum:** {report['status']}")
                st.write(f"**Not:** {report['note'] or 'Not yok'}")
                st.caption("Fotoğraf, mevcut insan inceleme/görüntü analizi akışına aktarılmak üzere burada doğrulanır; bu prototip vatandaş kaydını yerel gözlem dosyasına otomatik eklemez.")


st.set_page_config(page_title='AquaLitter | Kıyı gözlem ve temizlik planı', page_icon='🌊', layout='wide')
preserve_ui_values()
page = shell()
{
    PAGES[0]: render_overview_page,
    PAGES[1]: render_analysis_page,
    PAGES[2]: render_observation_page,
    PAGES[3]: render_route_page,
    PAGES[4]: render_environment_page,
    PAGES[5]: render_citizen_reports_page,
}[page]()
