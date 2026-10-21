import hashlib
import uuid
from django.shortcuts import render
from django.conf import settings
from django.core.cache import cache
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from fuel_router.serializers import RouteTripQuerySerializer
from fuel_router.services.planner import plan_trip, get_trip_cache_key
from fuel_router.services.optimizer import UnreachableRouteError
from fuel_router.services.spatial import spatial_index


@api_view(['GET'])
def api_root(request):
    """
    API Discovery Root endpoint providing metadata, available resources, and vehicle defaults.
    """
    return Response({
        "name": "Fuel Route Planner API",
        "version": "1.0.0",
        "description": "Calculates cost-optimal refueling stops along US highway routes respecting a 500-mile vehicle range.",
        "endpoints": {
            "plan_route": "/api/v1/route/plan/?start={start}&finish={finish}",
            "optimize_route_alias": "/api/v1/route/optimize/?start={start}&finish={finish}",
            "health": "/api/v1/health/",
            "interactive_map": "/map/",
        },
        "constraints": {
            "vehicle_max_range_miles": getattr(settings, "VEHICLE_MAX_RANGE_MILES", 500.0),
            "vehicle_mpg": getattr(settings, "VEHICLE_MPG", 10.0),
            "departure_tank": "full (50.0 gallons)",
        },
    })


@api_view(['GET'])
def health_check(request):
    """
    Service health and dependency readiness check.
    Reports operational status of the in-memory spatial index and routing engine.
    """
    spatial_ready = spatial_index.is_loaded
    station_count = len(spatial_index.stations) if spatial_ready and spatial_index.stations is not None else 0
    cities_count = len(spatial_index.cities_map) if spatial_ready and spatial_index.cities_map is not None else 0

    checks = {
        "spatial_index": {
            "status": "ready" if spatial_ready else "not_loaded",
            "indexed_stations": station_count,
            "indexed_cities": cities_count,
        },
        "routing_engine": {
            "status": "configured",
            "provider": "OSRM",
            "url": getattr(settings, "ROUTING_SERVICE_URL", "https://router.project-osrm.org"),
        },
        "cache": {
            "backend": settings.CACHES["default"]["BACKEND"].split(".")[-1],
            "ttl_seconds": getattr(settings, "CACHE_TTL_SECONDS", 3600),
        },
    }

    healthy = spatial_ready and station_count > 0
    return Response({
        "status": "healthy" if healthy else "degraded",
        "service": "fuel_router",
        "django_version": "6.1.2",
        "checks": checks,
    }, status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(['GET'])
def plan_fuel_route(request):
    """
    Receives trip start and finish queries, validates input via DRF,
    and returns a GeoJSON FeatureCollection of the driving route with optimal fuel stops.
    Supports HTTP Caching (ETag, If-None-Match, Cache-Control).
    """
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]

    serializer = RouteTripQuerySerializer(data=request.query_params)
    if not serializer.is_valid():
        response = Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        response["X-Request-ID"] = request_id
        return response

    start = serializer.validated_data["start"]
    finish = serializer.validated_data["finish"]

    max_range = float(getattr(settings, "VEHICLE_MAX_RANGE_MILES", 500.0))
    mpg = float(getattr(settings, "VEHICLE_MPG", 10.0))
    cache_ttl = int(getattr(settings, "CACHE_TTL_SECONDS", 3600))

    cache_key = get_trip_cache_key(start, finish, max_range=max_range, mpg=mpg)
    etag = f'"{hashlib.md5(cache_key.encode("utf-8")).hexdigest()}"'

    # Check conditional GET header (If-None-Match)
    if_none_match = request.headers.get("If-None-Match") or request.META.get("HTTP_IF_NONE_MATCH")
    if if_none_match and if_none_match.strip() == etag:
        response = Response(status=status.HTTP_304_NOT_MODIFIED)
        response["ETag"] = etag
        response["Cache-Control"] = f"public, max-age={cache_ttl}"
        response["X-Request-ID"] = request_id
        response["X-API-Version"] = "1.0"
        return response

    # Check in-memory cache
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        response = Response(cached_data, status=status.HTTP_200_OK)
        response["ETag"] = etag
        response["Cache-Control"] = f"public, max-age={cache_ttl}"
        response["X-Request-ID"] = request_id
        response["X-API-Version"] = "1.0"
        return response

    try:
        trip_geojson = plan_trip(start, finish)
    except ValueError as exc:
        return Response({
            "type": "https://localhost:8000/errors/bad-request",
            "title": "Invalid Route Parameters",
            "detail": str(exc),
            "error": str(exc),
            "status": status.HTTP_400_BAD_REQUEST,
        }, status=status.HTTP_400_BAD_REQUEST)
    except UnreachableRouteError as exc:
        return Response({
            "type": "https://localhost:8000/errors/unreachable-route",
            "title": "Unreachable Route",
            "detail": str(exc),
            "error": str(exc),
            "status": status.HTTP_422_UNPROCESSABLE_ENTITY,
        }, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

    cache.set(cache_key, trip_geojson, timeout=cache_ttl)

    response = Response(trip_geojson, status=status.HTTP_200_OK)
    response["ETag"] = etag
    response["Cache-Control"] = f"public, max-age={cache_ttl}"
    response["X-Request-ID"] = request_id
    response["X-API-Version"] = "1.0"
    return response


def map_view(request):
    """
    Renders an interactive Leaflet map interface for visual route exploration
    and fuel stop inspection.
    """
    start = request.GET.get("start", "Dallas, TX")
    finish = request.GET.get("finish", "Atlanta, GA")
    return render(request, "map.html", {
        "default_start": start,
        "default_finish": finish,
    })
