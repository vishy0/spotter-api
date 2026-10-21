from rest_framework.test import APITestCase
from rest_framework import status

class HealthCheckEndpointTest(APITestCase):
    def test_health_check_success(self):
        "Verify server health checks are running."
        response = self.client.get('/api/v1/health/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data.get("status"), "healthy")
        self.assertEqual(data.get("service"), "fuel_router")
