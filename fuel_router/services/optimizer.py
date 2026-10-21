from django.conf import settings
from scipy.spatial import KDTree
from fuel_router.services.spatial import spatial_index, haversine_distance_miles


class UnreachableRouteError(Exception):
    pass


def _calculate_cumulative_distances(coords: list[list[float]], total_distance_miles: float) -> list[float]:
    """
    Calculates cumulative distance from the start point for each coordinate in the polyline.
    Scales the haversine segment distances to match the total road distance from the routing service.
    """
    if not coords:
        return []

    raw_distances = [0.0]
    for i in range(1, len(coords)):
        lon1, lat1 = coords[i - 1]
        lon2, lat2 = coords[i]
        seg_dist = haversine_distance_miles(lat1, lon1, lat2, lon2)
        raw_distances.append(raw_distances[-1] + seg_dist)

    total_haversine = raw_distances[-1]
    if total_haversine > 0 and total_distance_miles > 0:
        scale = total_distance_miles / total_haversine
        return [round(d * scale, 3) for d in raw_distances]

    return raw_distances


def find_stations_along_route(
    coords: list[list[float]],
    total_distance_miles: float,
    sampling_step_miles: float = None,
    search_radius_miles: float = None,
) -> list[dict]:
    """
    Samples points along the driving polyline, finds nearby fuel stations from the spatial index,
    and projects each station to its approximate mile marker along the route.
    """
    if not coords or not spatial_index.is_loaded:
        return []

    if sampling_step_miles is None:
        sampling_step_miles = float(getattr(settings, "ROUTE_SAMPLING_STEP_MILES", 35.0))
    if search_radius_miles is None:
        search_radius_miles = float(getattr(settings, "ROUTE_SEARCH_RADIUS_MILES", 15.0))

    cum_distances = _calculate_cumulative_distances(coords, total_distance_miles)
    candidate_stations = {}

    # Sample points along the route based on distance intervals
    last_sampled_dist = -float("inf")
    sampled_points = []

    for i, pt in enumerate(coords):
        curr_dist = cum_distances[i]
        if curr_dist - last_sampled_dist >= sampling_step_miles or i == len(coords) - 1:
            sampled_points.append((pt[1], pt[0], curr_dist))  # (lat, lon, mile_marker)
            last_sampled_dist = curr_dist

    # Query stations around each sampled point
    for lat, lon, _ in sampled_points:
        nearby = spatial_index.query_radius(lat, lon, radius_miles=search_radius_miles)
        for st in nearby:
            station_id = st.get("opis_id") or f"{st['name']}_{st['lat']}_{st['lon']}"
            if station_id not in candidate_stations:
                candidate_stations[station_id] = st

    if not candidate_stations:
        return []

    # Project each station to its closest route coordinate to establish a 1D mile marker
    # We use a KDTree on the route coordinates for O(K log M) ultra-fast projection
    route_coords_lat_lon = [(pt[1], pt[0]) for pt in coords]
    route_tree = KDTree(route_coords_lat_lon)

    projected = []
    k_neighbors = min(3, len(coords))

    for st in candidate_stations.values():
        s_lat, s_lon = st["lat"], st["lon"]

        _, candidate_indices = route_tree.query([s_lat, s_lon], k=k_neighbors)
        if not hasattr(candidate_indices, "__iter__"):
            candidate_indices = [candidate_indices]

        closest_dist = float("inf")
        best_mile = 0.0

        for idx in candidate_indices:
            pt = coords[idx]
            d = haversine_distance_miles(s_lat, s_lon, pt[1], pt[0])
            if d < closest_dist:
                closest_dist = d
                best_mile = cum_distances[idx]

        # Station should be reasonably close to the highway
        if closest_dist <= search_radius_miles:
            station_copy = dict(st)
            station_copy["mile_marker"] = round(best_mile, 2)
            station_copy["off_route_distance"] = round(closest_dist, 2)
            projected.append(station_copy)

    # Sort strictly by cumulative mile marker along the route
    projected.sort(key=lambda s: s["mile_marker"])
    return projected


def _simulate_cheap_refueling(
    stations: list[dict],
    start_index: int,
    initial_fuel_miles: float,
    total_distance_miles: float,
    max_range: float,
    mpg: float,
) -> tuple[list[dict], float] | None:
    """
    Simulates greedy refueling path starting from a designated station.
    Returns (stops_list, total_cost) or None if the route is unreachable.
    """
    stops = []
    total_cost = 0.0

    curr_idx = start_index
    curr_station = stations[curr_idx]
    fuel_miles = initial_fuel_miles

    while curr_station["mile_marker"] < total_distance_miles:
        dist_to_dest = total_distance_miles - curr_station["mile_marker"]

        # Case 1: Destination is reachable with a full tank from here
        if dist_to_dest <= max_range:
            cheaper_ahead = None
            for j in range(curr_idx + 1, len(stations)):
                nxt = stations[j]
                if nxt["mile_marker"] > total_distance_miles:
                    break
                if nxt["mile_marker"] - curr_station["mile_marker"] <= max_range and nxt["price"] < curr_station["price"]:
                    cheaper_ahead = (j, nxt)
                    break

            if cheaper_ahead is None:
                # Buy only what is needed to reach the destination
                miles_needed = max(0.0, dist_to_dest - fuel_miles)
                gallons = round(miles_needed / mpg, 2)
                cost = round(gallons * curr_station["price"], 2)

                if gallons > 0:
                    stop_data = dict(curr_station)
                    stop_data["gallons_bought"] = gallons
                    stop_data["cost"] = cost
                    stops.append(stop_data)
                    total_cost += cost

                break  # Destination reached
            else:
                next_idx, next_station = cheaper_ahead
                leg_dist = next_station["mile_marker"] - curr_station["mile_marker"]
                miles_needed = max(0.0, leg_dist - fuel_miles)
                gallons = round(miles_needed / mpg, 2)
                cost = round(gallons * curr_station["price"], 2)

                if gallons > 0:
                    stop_data = dict(curr_station)
                    stop_data["gallons_bought"] = gallons
                    stop_data["cost"] = cost
                    stops.append(stop_data)
                    total_cost += cost
                    fuel_miles = 0.0
                else:
                    fuel_miles -= leg_dist

                curr_idx = next_idx
                curr_station = next_station
                continue

        # Case 2: Destination is beyond 500 miles, must find next stop within range
        reachable = []
        for j in range(curr_idx + 1, len(stations)):
            nxt = stations[j]
            leg_dist = nxt["mile_marker"] - curr_station["mile_marker"]
            if leg_dist > max_range:
                break
            reachable.append((j, nxt))

        if not reachable:
            return None  # Dead end: station gap exceeds max range

        # Check for cheaper stations within range
        cheaper_station = None
        for j, nxt in reachable:
            if nxt["price"] < curr_station["price"]:
                cheaper_station = (j, nxt)
                break

        if cheaper_station:
            next_idx, next_station = cheaper_station
            leg_dist = next_station["mile_marker"] - curr_station["mile_marker"]
            miles_needed = max(0.0, leg_dist - fuel_miles)
            gallons = round(miles_needed / mpg, 2)
            cost = round(gallons * curr_station["price"], 2)

            if gallons > 0:
                stop_data = dict(curr_station)
                stop_data["gallons_bought"] = gallons
                stop_data["cost"] = cost
                stops.append(stop_data)
                total_cost += cost
                fuel_miles = 0.0
            else:
                fuel_miles -= leg_dist

            curr_idx = next_idx
            curr_station = next_station
        else:
            # Fill the tank completely and jump to the cheapest available station
            miles_needed = max(0.0, max_range - fuel_miles)
            gallons = round(miles_needed / mpg, 2)
            cost = round(gallons * curr_station["price"], 2)

            stop_data = dict(curr_station)
            stop_data["gallons_bought"] = gallons
            stop_data["cost"] = cost
            stops.append(stop_data)
            total_cost += cost

            # Pick the lowest priced station within range (furthest if tied)
            best_idx, best_station = min(
                reachable,
                key=lambda item: (item[1]["price"], -item[1]["mile_marker"])
            )
            leg_dist = best_station["mile_marker"] - curr_station["mile_marker"]
            fuel_miles = max_range - leg_dist
            curr_idx = best_idx
            curr_station = best_station

    return stops, round(total_cost, 2)


def optimize_fuel_stops(coords: list[list[float]], total_distance_miles: float) -> dict:
    """
    Optimizes fuel stop locations along a route based on fuel prices, 500-mile vehicle range,
    and a starting full tank.
    """
    max_range = float(getattr(settings, "VEHICLE_MAX_RANGE_MILES", 500.0))
    mpg = float(getattr(settings, "VEHICLE_MPG", 10.0))

    # Short routes under max range require zero stops and cost $0
    if total_distance_miles <= max_range:
        return {
            "stops": [],
            "total_fuel_cost": 0.0,
            "total_gallons": 0.0,
            "total_stops": 0,
            "route_distance_miles": total_distance_miles,
        }

    stations = find_stations_along_route(coords, total_distance_miles)

    if not stations:
        raise UnreachableRouteError("No fuel stations located along the selected route.")

    # Stations reachable from start with the full departure tank
    candidate_first_stops = [
        (idx, st) for idx, st in enumerate(stations)
        if 0 < st["mile_marker"] <= max_range
    ]

    if not candidate_first_stops:
        raise UnreachableRouteError("First station gap exceeds the maximum vehicle range of 500 miles.")

    best_plan = None
    min_total_cost = float("inf")

    # Evaluate all candidate first stops to find the globally optimal refueling route
    for idx, st in candidate_first_stops:
        initial_fuel = max_range - st["mile_marker"]
        res = _simulate_cheap_refueling(
            stations,
            start_index=idx,
            initial_fuel_miles=initial_fuel,
            total_distance_miles=total_distance_miles,
            max_range=max_range,
            mpg=mpg,
        )
        if res is not None:
            stops, cost = res
            if cost < min_total_cost:
                min_total_cost = cost
                best_plan = stops

    if best_plan is None:
        raise UnreachableRouteError("Distance between consecutive fuel stations exceeds maximum vehicle range.")

    total_gallons = sum(s.get("gallons_bought", 0.0) for s in best_plan)

    return {
        "stops": best_plan,
        "total_fuel_cost": round(min_total_cost, 2),
        "total_gallons": round(total_gallons, 2),
        "total_stops": len(best_plan),
        "route_distance_miles": total_distance_miles,
    }
