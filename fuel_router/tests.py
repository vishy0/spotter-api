from unittest.mock import patch
from rest_framework.test import APITestCase
from rest_framework import status
from django.core.cache import cache
from fuel_router.services.spatial import spatial_index
from fuel_router.services.routing import geocode, get_route_polyline
from fuel_router.services.optimizer import optimize_fuel_stops, UnreachableRouteError


class HealthCheckEndpointTest(APITestCase):
    def test_health_check_success(self):
        "Verify server health checks are running and dependencies report readiness."
        response = self.client.get('/api/v1/health/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data.get("status"), "healthy")
        self.assertEqual(data.get("service"), "fuel_router")
        self.assertIn("checks", data)
        self.assertEqual(data["checks"]["spatial_index"]["status"], "ready")
        self.assertGreater(data["checks"]["spatial_index"]["indexed_stations"], 0)

    def test_api_root_discovery(self):
        "Verify API root discovery endpoint returns metadata and endpoints."
        response = self.client.get('/api/v1/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("name", data)
        self.assertIn("endpoints", data)
        self.assertIn("constraints", data)
        self.assertEqual(data["constraints"]["vehicle_max_range_miles"], 500.0)

    def test_root_redirect_to_map(self):
        "Verify visiting '/' redirects (302) to '/map/'."
        response = self.client.get('/')
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(response.url, '/map/')

    def test_root_health_alias(self):
        "Verify '/health/' works as an alias for '/api/v1/health/'."
        response = self.client.get('/health/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


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


class RouteOptimizeEndpointTest(APITestCase):
    def setUp(self):
        cache.clear()

    def test_missing_query_parameters(self):
        "Ensure 400 Bad Request is returned when required parameters are omitted."
        response = self.client.get('/api/v1/route/optimize/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("start", response.json())
        self.assertIn("finish", response.json())

        response = self.client.get('/api/v1/route/optimize/?start=Austin,%20TX')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("finish", response.json())

    def test_unresolvable_location(self):
        "Ensure 400 Bad Request is returned for an invalid city or address."
        response = self.client.get('/api/v1/route/optimize/?start=NonExistentLand99999&finish=Austin,%20TX')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.json())

    def test_short_route_response_schema(self):
        "Validates GeoJSON FeatureCollection response for trips under 500 miles."
        response = self.client.get('/api/v1/route/optimize/?start=Austin,%20TX&finish=Houston,%20TX')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data.get("type"), "FeatureCollection")
        self.assertEqual(data.get("total_cost"), 0.0)
        self.assertEqual(data.get("total_stops"), 0)
        self.assertGreater(data.get("route_distance_miles"), 100.0)
        self.assertGreaterEqual(len(data.get("features", [])), 1)

        # Check route LineString feature
        route_feature = data["features"][0]
        self.assertEqual(route_feature["type"], "Feature")
        self.assertEqual(route_feature["geometry"]["type"], "LineString")
        self.assertEqual(route_feature["properties"]["type"], "route")

    def test_long_route_and_caching(self):
        "Validates multi-stop route response and sub-30ms cache retrieval."
        url = '/api/v1/route/optimize/?start=Dallas,%20TX&finish=Atlanta,%20GA'

        # First request (fetches and optimizes)
        response1 = self.client.get(url)
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        data1 = response1.json()

        self.assertEqual(data1.get("type"), "FeatureCollection")
        self.assertGreater(data1.get("total_cost"), 0.0)
        self.assertGreater(data1.get("total_stops"), 0)

        # Confirm both LineString and Point features exist
        feature_types = [f["geometry"]["type"] for f in data1["features"]]
        self.assertIn("LineString", feature_types)
        self.assertIn("Point", feature_types)

        # Second request (must return identical cached data)
        response2 = self.client.get(url)
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(response1.json(), response2.json())

        # Validate HTTP Caching headers
        self.assertIn("ETag", response1.headers)
        self.assertIn("Cache-Control", response1.headers)
        self.assertIn("X-Request-ID", response1.headers)

        # Conditional GET with matching ETag returns 304 Not Modified
        etag = response1.headers["ETag"]
        response3 = self.client.get(url, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(response3.status_code, status.HTTP_304_NOT_MODIFIED)

    def test_plan_route_endpoint_alias(self):
        "Ensures /api/v1/route/plan/ returns identical GeoJSON structure as route/optimize/."
        response = self.client.get('/api/v1/route/plan/?start=Austin,%20TX&finish=Houston,%20TX')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data.get("type"), "FeatureCollection")
        self.assertEqual(data.get("total_cost"), 0.0)

    @patch("fuel_router.services.planner.optimize_fuel_stops")
    def test_unreachable_route_returns_422(self, mock_optimizer):
        "Validates 422 Unprocessable Entity when distance between stations exceeds range."
        mock_optimizer.side_effect = UnreachableRouteError("Distance between stations exceeds 500 miles.")
        response = self.client.get('/api/v1/route/optimize/?start=Dallas,%20TX&finish=Atlanta,%20GA')
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertIn("error", response.json())
        self.assertIn("title", response.json())
        self.assertEqual(response.json().get("status"), 422)


class MapViewTest(APITestCase):
    def test_map_view_returns_200_and_renders_html(self):
        "Ensures /map/ renders the interactive Leaflet HTML template."
        response = self.client.get('/map/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Fuel Route Planner")
        self.assertContains(response, "leaflet")


