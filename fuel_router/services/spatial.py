import csv
import math
import logging
from pathlib import Path
from scipy.spatial import KDTree

logger = logging.getLogger(__name__)

EARTH_RADIUS_MILES = 3958.8


def haversine_distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_MILES * c


def normalize_city(city: str) -> str:
    if not city:
        return ""
    clean = city.strip().lower().replace(".", "").replace("'", "")
    # Common abbreviation expansions
    if clean.startswith("st "):
        clean = "saint " + clean[3:]
    elif clean.startswith("mt "):
        clean = "mount " + clean[3:]
    elif clean.startswith("ft "):
        clean = "fort " + clean[3:]
    return clean


def normalize_state(state: str) -> str:
    return state.strip().upper() if state else ""


class SpatialIndex:
    """
    In-memory spatial index powered by scipy.spatial.KDTree.
    """

    def __init__(self):
        self.tree = None
        self.stations = []
        self._is_loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    def load(self, cities_path: Path, fuel_path: Path) -> int:
        """
        Merge cities and fuel prices datasets and construct KDTree.
        """
        if self._is_loaded:
            return len(self.stations)

        if not cities_path.exists() or not fuel_path.exists():
            logger.warning(
                f"Data files missing. Cities exists: {cities_path.exists()}, "
                f"Fuel exists: {fuel_path.exists()}"
            )
            return 0

        cities_map = {}
        with open(cities_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                city = normalize_city(row.get("CITY", ""))
                state = normalize_state(row.get("STATE_CODE", ""))
                lat_str = row.get("LATITUDE")
                lon_str = row.get("LONGITUDE")
                if city and state and lat_str and lon_str:
                    try:
                        cities_map[(city, state)] = (float(lat_str), float(lon_str))
                    except ValueError:
                        continue

        matched_stations = []
        station_coords = []

        with open(fuel_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                raw_city = row.get("City", "")
                raw_state = row.get("State", "")
                city_key = normalize_city(raw_city)
                state_key = normalize_state(raw_state)

                coords = cities_map.get((city_key, state_key))
                if not coords:
                    continue

                price_str = row.get("Retail Price", "")
                try:
                    price = float(price_str)
                except (ValueError, TypeError):
                    continue

                lat, lon = coords
                station_data = {
                    "opis_id": row.get("OPIS Truckstop ID", "").strip(),
                    "name": row.get("Truckstop Name", "").strip(),
                    "address": row.get("Address", "").strip(),
                    "city": raw_city.strip(),
                    "state": raw_state.strip(),
                    "price": price,
                    "lat": lat,
                    "lon": lon,
                }
                matched_stations.append(station_data)
                station_coords.append([lat, lon])

        if station_coords:
            self.tree = KDTree(station_coords)
            self.stations = matched_stations
            self._is_loaded = True
            logger.info(f"SpatialIndex loaded {len(self.stations)} fuel stations.")

        return len(self.stations)

    def query_radius(self, lat: float, lon: float, radius_miles: float) -> list[dict]:
        """
        Query stations within radius_miles of (lat, lon).
        """
        if not self._is_loaded or self.tree is None:
            return []

        deg_radius = radius_miles / 50.0
        candidate_indices = self.tree.query_ball_point([lat, lon], r=deg_radius)

        results = []
        for idx in candidate_indices:
            station = self.stations[idx]
            dist = haversine_distance_miles(lat, lon, station["lat"], station["lon"])
            if dist <= radius_miles:
                station_with_dist = dict(station)
                station_with_dist["distance_miles"] = round(dist, 2)
                results.append(station_with_dist)

        results.sort(key=lambda s: s["distance_miles"])
        return results


spatial_index = SpatialIndex()
