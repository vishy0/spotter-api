import hashlib
from fuel_router.services.routing import geocode, get_route_polyline
from fuel_router.services.optimizer import optimize_fuel_stops, UnreachableRouteError


def get_trip_cache_key(start: str, finish: str) -> str:
    """Generates a deterministic cache key for a given start and destination pair."""
    token = f"{start.strip().lower()}:{finish.strip().lower()}"
    return "trip_route_" + hashlib.md5(token.encode("utf-8")).hexdigest()


def build_trip_geojson(start: str, finish: str, route_data: dict, fuel_plan: dict) -> dict:
    """Constructs a GeoJSON FeatureCollection containing the road geometry and fuel stop points."""
    features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": route_data["coordinates"],
            },
            "properties": {
                "type": "route",
                "start": start,
                "finish": finish,
                "distance_miles": route_data["distance_miles"],
                "duration_seconds": route_data.get("duration_seconds", 0.0),
            },
        }
    ]

    for stop in fuel_plan.get("stops", []):
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [stop["lon"], stop["lat"]],
            },
            "properties": {
                "type": "fuel_stop",
                "name": stop["name"],
                "address": stop["address"],
                "city": stop["city"],
                "state": stop["state"],
                "price": stop["price"],
                "mile_marker": stop["mile_marker"],
                "gallons_bought": stop["gallons_bought"],
                "cost": stop["cost"],
            },
        })

    return {
        "type": "FeatureCollection",
        "total_cost": fuel_plan["total_fuel_cost"],
        "total_gallons": fuel_plan["total_gallons"],
        "total_stops": fuel_plan["total_stops"],
        "route_distance_miles": fuel_plan["route_distance_miles"],
        "features": features,
    }


def plan_trip(start: str, finish: str) -> dict:
    """
    Coordinates the full trip planning pipeline: geocoding, route retrieval,
    fuel stop calculation, and GeoJSON serialization.
    """
    start_coords = geocode(start)
    finish_coords = geocode(finish)

    route_data = get_route_polyline(start_coords, finish_coords)
    fuel_plan = optimize_fuel_stops(route_data["coordinates"], route_data["distance_miles"])

    return build_trip_geojson(start, finish, route_data, fuel_plan)
