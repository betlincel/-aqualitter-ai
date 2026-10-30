"""Integration checks using the user's local official ZIP, without changing records."""

import unittest
from pathlib import Path

from coastline import MIN_COAST_CLEARANCE_KM, load_natural_earth_zip
from marine_routes import (
    DEMO_SCENARIO_NODES,
    DEMO_VESSEL_NODES,
    RouteNotAvailable,
    build_land_checked_links,
    compare_visit_orders,
    haversine_km,
)


class RealZipScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).resolve().parents[1] / "data" / "ne_10m_land.zip"
        if not source.is_file():
            raise unittest.SkipTest("Local Natural Earth ZIP is required; no download attempted.")
        cls.mask = load_natural_earth_zip(source)
        cls.nodes = {**DEMO_VESSEL_NODES, **DEMO_SCENARIO_NODES}
        cls.links, cls.unavailable = build_land_checked_links(cls.nodes, cls.mask)

    def test_all_six_visits_vessels_and_all_links_pass_unchanged_clearance(self):
        self.assertEqual(MIN_COAST_CLEARANCE_KM, 1.0)
        self.assertEqual(self.mask.clearance_km, 1.0)
        self.assertEqual(len(DEMO_SCENARIO_NODES), 6)
        self.assertFalse(self.unavailable)
        self.assertEqual(len(self.links), 8 * 7)
        for node in self.nodes.values():
            self.assertIsNone(self.mask.validate_path([(node['latitude'], node['longitude'])]))
        for path in self.links.values():
            self.assertIsNone(self.mask.validate_path(path))

    def test_same_six_visits_and_endpoints_with_distance_from_rendered_geometry(self):
        visits = [f"scenario-demo-{letter}" for letter in "fbdace"]
        result = compare_visit_orders(
            "vessel-west", "vessel-west", visits, self.links, self.unavailable
        )
        self.assertTrue(result["improved"])
        for prefix in ("current", "recommended"):
            self.assertCountEqual(result[f"{prefix}_order"], visits)
            self.assertEqual(len(result[f"{prefix}_order"]), len(set(visits)))
            self.assertEqual(result[f"{prefix}_nodes"][0], "vessel-west")
            self.assertEqual(result[f"{prefix}_nodes"][-1], "vessel-west")
            drawn_distance = sum(
                haversine_km(a, b)
                for leg in result[f"{prefix}_legs"]
                for a, b in zip(leg['coordinates'], leg['coordinates'][1:])
            )
            self.assertAlmostEqual(result[f"{prefix}_km"], drawn_distance, places=9)
        self.assertAlmostEqual(
            result['difference_km'], result['current_km'] - result['recommended_km']
        )

    def test_original_invalid_point_is_still_rejected_without_relocation(self):
        original = (41.008, 39.720)
        self.assertIn("kara", self.mask.validate_path([original]))
        nodes = {**self.nodes, "invalid-visit": dict(latitude=original[0], longitude=original[1])}
        links, unavailable = build_land_checked_links(nodes, self.mask)
        self.assertIn("invalid-visit", unavailable)
        with self.assertRaises(RouteNotAvailable):
            compare_visit_orders("vessel-west", "vessel-west", ["invalid-visit"], links, unavailable)
        self.assertEqual((nodes['invalid-visit']['latitude'], nodes['invalid-visit']['longitude']), original)


if __name__ == "__main__":
    unittest.main()
