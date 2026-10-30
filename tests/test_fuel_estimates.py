import math
import unittest

from fuel_estimates import DIESEL_KG_CO2_PER_LITER, compare_fuel_co2


class FuelEstimateTests(unittest.TestCase):
    def test_nautical_miles_liters_and_kg_co2_units(self):
        result = compare_fuel_co2(18.52, 9.26, 2.0)
        self.assertAlmostEqual(result['current']['distance_nm'], 10.0)
        self.assertAlmostEqual(result['current']['fuel_l'], 20.0)
        self.assertAlmostEqual(result['current']['co2_kg'], 20 * (10.21 / 3.785411784))
        self.assertAlmostEqual(result['difference']['fuel_l'], 10.0)
        self.assertAlmostEqual(result['difference']['co2_kg'], 10 * DIESEL_KG_CO2_PER_LITER)

    def test_equal_routes_and_zero_distance_have_zero_difference(self):
        for distance in (0.0, 39.22031396657271):
            result = compare_fuel_co2(distance, distance, 1.23456789)
            self.assertEqual(result['difference'], dict(fuel_l=0.0, co2_kg=0.0))

    def test_unrounded_distances_consumption_and_factor_are_used(self):
        current, recommended, rate = 64.37911378355338, 39.22031396657271, 1.23456789
        result = compare_fuel_co2(current, recommended, rate)
        self.assertEqual(result['current']['fuel_l'], current / 1.852 * rate)
        self.assertEqual(result['recommended']['co2_kg'], recommended / 1.852 * rate * (10.21 / 3.785411784))
        self.assertNotEqual(result['current']['fuel_l'], round(current / 1.852, 2) * rate)

    def test_changes_in_consumption_and_signed_difference_are_recomputed(self):
        one = compare_fuel_co2(1.852, 3.704, 1.0)
        two = compare_fuel_co2(1.852, 3.704, 2.0)
        self.assertEqual(one['difference']['fuel_l'], -1.0)
        self.assertEqual(two['current']['fuel_l'], 2 * one['current']['fuel_l'])

    def test_invalid_inputs_do_not_produce_estimates(self):
        for invalid in (None, True, 'abc', '2', -1.0, math.nan, math.inf, -math.inf):
            for index in (0, 1, 2, 3):
                with self.subTest(invalid=invalid, index=index):
                    args = [18.52, 9.26, 2.0, DIESEL_KG_CO2_PER_LITER]
                    args[index] = invalid
                    with self.assertRaises(ValueError):
                        compare_fuel_co2(*args)
        for index in (2, 3):
            args = [18.52, 9.26, 2.0, DIESEL_KG_CO2_PER_LITER]
            args[index] = 0.0
            with self.assertRaises(ValueError):
                compare_fuel_co2(*args)
        with self.assertRaises(ValueError):
            compare_fuel_co2(1e308, 1.0, 1e308)


if __name__ == '__main__':
    unittest.main()
