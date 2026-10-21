from rest_framework.test import APITestCase
from rest_framework import status
from fuel_router.services.spatial import spatial_index
from fuel_router.services.routing import geocode, get_route_polyline
from fuel_router.services.optimizer import optimize_fuel_stops, UnreachableRouteError


class HealthCheckEndpointTest(APITestCase):
    def test_health_check_success(self):
        "Verify server health checks are running."
        response = self.client.get('/api/v1/health/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data.get("status"), "healthy")
        self.assertEqual(data.get("service"), "fuel_router")


class SpatialIndexTest(APITestCase):
    def test_kdtree_spatial_query_dallas(self):
        self.assertTrue(spatial_index.is_loaded, "SpatialIndex should be loaded on boot")
        self.assertGreater(len(spatial_index.stations), 0, "Stations list should not be empty")

        # Dallas, TX coordinates
        dallas_lat = 32.7767
        dallas_lon = -96.7970
        nearby_stations = spatial_index.query_radius(dallas_lat, dallas_lon, radius_miles=50.0)

        self.assertGreater(len(nearby_stations), 0, "Expected stations within 50 miles of Dallas")
        first_station = nearby_stations[0]
        self.assertIn("name", first_station)
        self.assertIn("price", first_station)
        self.assertIn("lat", first_station)
        self.assertIn("lon", first_station)
        self.assertIn("distance_miles", first_station)
        self.assertLessEqual(first_station["distance_miles"], 50.0)


class RoutingServiceTest(APITestCase):
    def test_geocode_los_angeles(self):
        "Ensure geocoding resolves city coordinates accurately."
        coords = geocode("Los Angeles, CA")
        self.assertEqual(len(coords), 2)
        lon, lat = coords
        
        # Approximate Longitude around -118.24, Latitude around 34.05
        self.assertAlmostEqual(lon, -118.24, delta=0.1)
        self.assertAlmostEqual(lat, 34.05, delta=0.1)

    def test_get_route_polyline_austin_to_houston(self):
        "Ensure route polyline and distance calculation between Austin and Houston."
        austin = [-97.7431, 30.2672]
        houston = [-95.3698, 29.7604]

        route_data = get_route_polyline(austin, houston)
        self.assertEqual(route_data["type"], "LineString")
        self.assertGreater(len(route_data["coordinates"]), 10)
        self.assertGreater(route_data["distance_miles"], 130)
        self.assertLess(route_data["distance_miles"], 200)


class FuelOptimizerTest(APITestCase):
    def test_short_route_requires_zero_stops(self):
        "Trips under 500 miles require zero stops and zero additional fuel expenditure."
        austin = [-97.7431, 30.2672]
        houston = [-95.3698, 29.7604]

        route_data = get_route_polyline(austin, houston)
        result = optimize_fuel_stops(route_data["coordinates"], route_data["distance_miles"])

        self.assertEqual(result["total_stops"], 0)
        self.assertEqual(result["total_fuel_cost"], 0.0)
        self.assertEqual(result["total_gallons"], 0.0)
        self.assertEqual(len(result["stops"]), 0)

    def test_long_route_refueling_optimization(self):
        "Long routes calculate valid fuel stops respecting range and pricing."
        dallas = [-96.7970, 32.7767]
        atlanta = [-84.3880, 33.7490]

        route_data = get_route_polyline(dallas, atlanta)
        result = optimize_fuel_stops(route_data["coordinates"], route_data["distance_miles"])

        self.assertGreater(result["total_stops"], 0)
        self.assertGreater(result["total_fuel_cost"], 0.0)
        self.assertGreater(result["total_gallons"], 0.0)

        prev_mile = 0.0
        for stop in result["stops"]:
            self.assertIn("name", stop)
            self.assertIn("price", stop)
            self.assertIn("gallons_bought", stop)
            self.assertGreater(stop["gallons_bought"], 0.0)
            self.assertLessEqual(stop["mile_marker"] - prev_mile, 500.0)
            prev_mile = stop["mile_marker"]

        self.assertLessEqual(route_data["distance_miles"] - prev_mile, 500.0)

    def test_unreachable_route_raises_exception(self):
        "Routes through areas without accessible stations raise an UnreachableRouteError."
        empty_ocean_coords = [[-65.0, 25.0], [-66.0, 26.0]]
        with self.assertRaises(UnreachableRouteError):
            optimize_fuel_stops(empty_ocean_coords, total_distance_miles=800.0)
