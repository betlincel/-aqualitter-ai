import unittest
import struct
import tempfile
import zipfile
from pathlib import Path

from coastline import LandMask, load_natural_earth_zip
from marine_routes import (
    DEMO_VESSEL_NODES,
    RouteNotAvailable,
    build_land_checked_links,
    compare_visit_orders,
    haversine_km,
)


def land_mask(top_latitude=41.03, clearance_km=0.5):
    return LandMask.from_geojson(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [39.65, 40.98],
                            [39.86, 40.98],
                            [39.86, top_latitude],
                            [39.65, top_latitude],
                            [39.65, 40.98],
                        ]],
                    },
                }
            ],
        },
        clearance_km=clearance_km,
    )


class CoastlineRouteTests(unittest.TestCase):
    def test_local_land_shapefile_zip_is_loaded_and_checked(self):
        ring = [(39.70, 41.00), (39.74, 41.00), (39.74, 41.03), (39.70, 41.03), (39.70, 41.00)]
        longitudes = [point[0] for point in ring]
        latitudes = [point[1] for point in ring]
        bbox = (min(longitudes), min(latitudes), max(longitudes), max(latitudes))
        content = bytearray(struct.pack("<i", 5))
        content.extend(struct.pack("<4d", *bbox))
        content.extend(struct.pack("<2i", 1, len(ring)))
        content.extend(struct.pack("<i", 0))
        for point in ring:
            content.extend(struct.pack("<2d", *point))
        header = bytearray(100)
        struct.pack_into(">i", header, 0, 9994)
        struct.pack_into(">i", header, 24, (100 + 8 + len(content)) // 2)
        struct.pack_into("<i", header, 28, 1000)
        struct.pack_into("<i", header, 32, 5)
        struct.pack_into("<4d", header, 36, *bbox)
        shp = bytes(header) + struct.pack(">2i", 1, len(content) // 2) + bytes(content)

        with tempfile.TemporaryDirectory() as directory:
            zip_path = Path(directory) / "land.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("ne_10m_land.shp", shp)
                archive.writestr("ne_10m_land.prj", 'GEOGCS["GCS_WGS_1984"]')
            mask = load_natural_earth_zip(zip_path, clearance_km=0.1)

        self.assertIn("kara", mask.validate_path([(41.01, 39.72)]).lower())

    def test_line_crossing_land_is_rejected(self):
        mask = LandMask.from_geojson(
            {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "properties": {},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [39.73, 41.043], [39.75, 41.043],
                            [39.75, 41.047], [39.73, 41.047],
                            [39.73, 41.043],
                        ]],
                    },
                }],
            },
            clearance_km=0.1,
        )

        reason = mask.validate_path([(41.045, 39.70), (41.045, 39.78)])
        self.assertIsNotNone(reason)
        self.assertIn("kesi", reason.lower())

    def test_blocked_connection_is_omitted_from_route_graph(self):
        mask = LandMask.from_geojson(
            {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "properties": {},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [39.73, 41.043], [39.75, 41.043],
                            [39.75, 41.047], [39.73, 41.047],
                            [39.73, 41.043],
                        ]],
                    },
                }],
            },
            clearance_km=0.1,
        )
        links, unavailable = build_land_checked_links(DEMO_VESSEL_NODES, mask)

        self.assertNotIn(("vessel-west", "vessel-east"), links)
        with self.assertRaisesRegex(RouteNotAvailable, "kesi"):
            compare_visit_orders(
                "vessel-west", "vessel-east", [], links=links, unavailable=unavailable
            )

    def test_added_approved_observation_joins_only_after_land_checks(self):
        # This is an in-memory test observation. The ignored user JSON is never opened or written.
        user_observation = {
            "observation_id": "real-observation-test",
            "record_type": "real",
            "location": {"latitude": 41.06, "longitude": 39.75},
            "approved_detections": [{"label": "plastic bottle"}],
        }
        nodes = {
            **DEMO_VESSEL_NODES,
            user_observation["observation_id"]: {
                "label": "Gerçek gözlem",
                **user_observation["location"],
            },
        }
        links, unavailable = build_land_checked_links(nodes, land_mask())
        result = compare_visit_orders(
            "vessel-west",
            "vessel-east",
            [user_observation["observation_id"]],
            links=links,
            unavailable=unavailable,
        )

        self.assertIn(user_observation["observation_id"], result["current_nodes"])
        self.assertEqual(result["current_order"], ["real-observation-test"])
        self.assertGreater(result["current_km"], 0)

    def test_land_or_near_coast_observation_is_unavailable_without_relocation(self):
        mask = land_mask(clearance_km=1.0)
        land_point = (41.01, 39.72)
        near_coast_point = (41.035, 39.72)

        self.assertIn("kara", mask.validate_path([land_point]).lower())
        self.assertIn("tampon", mask.validate_path([near_coast_point]).lower())
        self.assertEqual(land_point, (41.01, 39.72))

    def test_drawn_route_legs_and_reported_distance_use_same_polyline(self):
        observation_id = "real-observation-test"
        nodes = {
            **DEMO_VESSEL_NODES,
            observation_id: {
                "label": "Gerçek gözlem",
                "latitude": 41.06,
                "longitude": 39.75,
            },
        }
        links, unavailable = build_land_checked_links(nodes, land_mask())
        result = compare_visit_orders(
            "vessel-west",
            "vessel-east",
            [observation_id],
            links=links,
            unavailable=unavailable,
        )
        rendered_leg_points = [
            point
            for leg in result["current_legs"]
            for point in zip(leg["coordinates"], leg["coordinates"][1:])
        ]
        rendered_distance = sum(haversine_km(start, end) for start, end in rendered_leg_points)

        self.assertAlmostEqual(result["current_km"], rendered_distance, places=8)

    def test_point_outside_trabzon_bounds_is_not_routed(self):
        mask = land_mask()
        self.assertIn("dışında", mask.validate_path([(41.2, 39.75)]).lower())


if __name__ == "__main__":
    unittest.main()
