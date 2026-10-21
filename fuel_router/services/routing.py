import os
import requests
from django.conf import settings
from fuel_router.services.spatial import spatial_index, normalize_city, normalize_state


def geocode(query: str) -> list[float]:
    """
    Geocodes a location query into [longitude, latitude] (GeoJSON format).
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
        "User-Agent": getattr(settings, "GEOCODING_USER_AGENT", "FuelRouterApp/1.0")
    }
    params = {
        "q": clean_query,
        "format": "json",
        "limit": 1,
        "countrycodes": "us",
    }
    nominatim_url = getattr(
        settings, "GEOCODING_SERVICE_URL", "https://nominatim.openstreetmap.org/search"
    )

    try:
        response = requests.get(nominatim_url, params=params, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        if data and len(data) > 0:
            lon = float(data[0]["lon"])
            lat = float(data[0]["lat"])
            return [round(lon, 4), round(lat, 4)]
    except Exception as exc:
        # external call fail and no local match found.
        pass

    raise ValueError(f"Unable to resolve coordinates for location: '{query}'")


def get_route_polyline(start_coords: list[float], finish_coords: list[float]) -> dict:
    """
    Fetches driving route polyline between start and finish coordinates.
    """
    if len(start_coords) != 2 or len(finish_coords) != 2:
        raise ValueError("Coordinates must be [longitude, latitude] pairs.")

    base_url = getattr(settings, "ROUTING_SERVICE_URL", None) or os.getenv(
        "ROUTING_SERVICE_URL", DEFAULT_ROUTING_URL
    ).rstrip("/")

    start_lon, start_lat = start_coords
    finish_lon, finish_lat = finish_coords

    url = f"{base_url}/route/v1/driving/{start_lon},{start_lat};{finish_lon},{finish_lat}"
    params = {
        "overview": "full",
        "geometries": "geojson",
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
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
