import unittest

from marine_routes import (
    DEMO_CORRIDOR_LATITUDE,
    RouteNotAvailable,
    compare_visit_orders,
    get_demo_link,
    haversine_km,
    repeated_edge_passes,
    route_distance_km,
)


class MarineRouteTests(unittest.TestCase):
    def test_optimizer_keeps_same_endpoints_and_visits_each_stop_once(self):
        result = compare_visit_orders(
            "vessel-west",
            "vessel-east",
            ["scenario-demo-b", "scenario-demo-a"],
        )

        self.assertEqual(result["current_nodes"][0], "vessel-west")
        self.assertEqual(result["current_nodes"][-1], "vessel-east")
        self.assertEqual(result["recommended_nodes"][0], "vessel-west")
        self.assertEqual(result["recommended_nodes"][-1], "vessel-east")
        self.assertCountEqual(result["recommended_order"], ["scenario-demo-a", "scenario-demo-b"])
        self.assertEqual(len(result["recommended_order"]), 2)
        self.assertTrue(result["improved"])
        self.assertGreater(result["improvement_km"], 0)

    def test_route_returns_to_selected_start_when_start_and_return_match(self):
        result = compare_visit_orders(
            "vessel-west",
            "vessel-west",
            ["scenario-demo-a", "scenario-demo-b"],
        )

        self.assertEqual(
            result["recommended_nodes"],
            ["vessel-west", *result["recommended_order"], "vessel-west"],
        )
        self.assertEqual(result["recommended_legs"][-1]["to"], "vessel-west")
        self.assertGreater(result["recommended_km"], 0)

    def test_revisited_connection_is_marked_for_distinct_map_rendering(self):
        result = compare_visit_orders(
            "vessel-west",
            "vessel-west",
            ["scenario-demo-a"],
        )

        self.assertEqual(repeated_edge_passes(result["current_legs"]), [(2, 1), (2, 2)])

    def test_already_best_order_reports_no_improvement(self):
        result = compare_visit_orders(
            "vessel-west",
            "vessel-east",
            ["scenario-demo-a", "scenario-demo-b"],
        )

        self.assertFalse(result["improved"])
        self.assertEqual(result["improvement_km"], 0.0)
        self.assertAlmostEqual(result["current_km"], result["recommended_km"])

    def test_unknown_or_unprepared_location_is_not_moved_or_connected(self):
        with self.assertRaises(RouteNotAvailable):
            compare_visit_orders(
                "vessel-west",
                "vessel-east",
                ["real-observation-without-demo-link"],
            )

    def test_distances_sum_prepared_polyline_segments_not_endpoint_chord(self):
        link = get_demo_link("vessel-west", "scenario-demo-a")
        total, legs = route_distance_km(["vessel-west", "scenario-demo-a"])
        segment_total = sum(haversine_km(a, b) for a, b in zip(link, link[1:]))
        endpoint_chord = haversine_km(link[0], link[-1])

        self.assertIn((DEMO_CORRIDOR_LATITUDE, 39.6900), link)
        self.assertAlmostEqual(total, segment_total, places=9)
        self.assertGreaterEqual(total, endpoint_chord)
        self.assertEqual(len(legs), 1)

    def test_haversine_uses_great_circle_kilometres(self):
        self.assertAlmostEqual(
            haversine_km((0.0, 0.0), (0.0, 1.0)),
            111.195,
            delta=0.01,
        )


if __name__ == "__main__":
    unittest.main()
