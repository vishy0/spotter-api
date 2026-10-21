from rest_framework.test import APITestCase
from rest_framework import status
from fuel_router.services.spatial import spatial_index


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

        self.assertGreater(len(nearby_stations), 0, "Expected at least one station within 50 miles of Dallas")

        # Validate station fields
        first_station = nearby_stations[0]
        self.assertIn("name", first_station)
        self.assertIn("price", first_station)
        self.assertIn("lat", first_station)
        self.assertIn("lon", first_station)
        self.assertIn("distance_miles", first_station)
        self.assertLessEqual(first_station["distance_miles"], 50.0)
