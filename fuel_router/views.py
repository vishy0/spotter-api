from rest_framework.decorators import api_view
from rest_framework.response import Response

@api_view(['GET'])
def health_check(request):
    "Simple health check endpoint to verify API and Django setup."
    return Response({
        "status": "healthy",
        "service": "fuel_router",
        "django_version": "6.1.2"
    })
