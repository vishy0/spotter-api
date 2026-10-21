import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from django.conf import settings
from fuel_router.services.spatial import spatial_index, normalize_city, normalize_state

DEFAULT_ROUTING_URL = "https://router.project-osrm.org"
DEFAULT_GEOCODING_URL = "https://nominatim.openstreetmap.org/search"

_session = None


def _get_session() -> requests.Session:
    """Returns a shared requests Session configured with connection pooling and backoff retries."""
    global _session
    if _session is None:
        _session = requests.Session()
        retries = Retry(
            total=2,
            backoff_factor=0.3,
            status_forcelist=[500, 502, 503, 504],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=20)
        _session.mount("https://", adapter)
        _session.mount("http://", adapter)
    return _session


def geocode(query: str) -> list[float]:
    """
    Geocodes a location query into [longitude, latitude] (GeoJSON format).
    Prioritizes fast in-memory spatial index (0ms) and falls back to Nominatim.
    """
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("Location query cannot be empty.")

    # Try local index if input looks like "City, State"
    if "," in clean_query and spatial_index.is_loaded:
        parts = clean_query.split(",", 1)
        city_norm = normalize_city(parts[0])
        state_norm = normalize_state(parts[1])

        coords = spatial_index.cities_map.get((city_norm, state_norm))
        if coords:
            lat, lon = coords
            # GeoJSON expects [lon, lat]
            return [round(lon, 4), round(lat, 4)]

    # Fallback to Nominatim for addresses or locations not found locally
    headers = {
        "User-Agent": getattr(settings, "GEOCODING_USER_AGENT", "FuelRouterApp/1.0 (contact: admin@fuelrouter.local)")
    }
    params = {
        "q": clean_query,
        "format": "json",
        "limit": 1,
        "countrycodes": "us",
    }
    nominatim_url = getattr(settings, "GEOCODING_SERVICE_URL", DEFAULT_GEOCODING_URL)
    timeout = getattr(settings, "GEOCODING_TIMEOUT_SECONDS", 5)

    try:
        session = _get_session()
        response = session.get(nominatim_url, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        if data and len(data) > 0:
            lon = float(data[0]["lon"])
            lat = float(data[0]["lat"])
            return [round(lon, 4), round(lat, 4)]
    except Exception:
        # external call fail and no local match found.
        pass

    raise ValueError(f"Unable to resolve coordinates for location: '{query}'")


def get_route_polyline(start_coords: list[float], finish_coords: list[float]) -> dict:
    """
    Fetches driving route polyline between start and finish coordinates via OSRM.
    """
    if len(start_coords) != 2 or len(finish_coords) != 2:
        raise ValueError("Coordinates must be [longitude, latitude] pairs.")

    base_url = (
        getattr(settings, "ROUTING_SERVICE_URL", None)
        or os.getenv("ROUTING_SERVICE_URL", DEFAULT_ROUTING_URL)
    ).rstrip("/")
    timeout = getattr(settings, "ROUTING_TIMEOUT_SECONDS", 10)

    start_lon, start_lat = start_coords
    finish_lon, finish_lat = finish_coords

    url = f"{base_url}/route/v1/driving/{start_lon},{start_lat};{finish_lon},{finish_lat}"
    params = {
        "overview": "full",
        "geometries": "geojson",
    }

    try:
        session = _get_session()
        resp = session.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as e:
        raise ValueError(f"Failed to connect to routing service: {e}")

    if payload.get("code") != "Ok" or not payload.get("routes"):
        msg = payload.get("message", "No route found between points")
        raise ValueError(f"Routing error: {msg}")

    route = payload["routes"][0]
    geometry = route["geometry"]
    distance_meters = route.get("distance", 0.0)
    duration_seconds = route.get("duration", 0.0)

    meters_to_miles = getattr(settings, "METERS_TO_MILES", 0.000621371)
    distance_miles = round(distance_meters * meters_to_miles, 2)

    return {
        "type": "LineString",
        "coordinates": geometry.get("coordinates", []),
        "distance_miles": distance_miles,
        "duration_seconds": duration_seconds,
    }
