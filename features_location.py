from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import pandas as pd

try:
    import requests  # type: ignore
except ModuleNotFoundError:
    requests = None  # type: ignore

try:
    from geopy.distance import geodesic
except ModuleNotFoundError:
    geodesic = None  # type: ignore

Coord = Tuple[float, float]


class LocationPlanner:
    def __init__(self, project_root: str = None):
        self.project_root = project_root or os.path.dirname(os.path.abspath(__file__))

    @staticmethod
    def _prompt_manual_coords(label: str) -> Optional[Coord]:
        print(f"\nManual coordinates entry for: {label}")
        print("Enter latitude/longitude (example: 1.3521, 103.8198).")
        raw = input("Lat,Lng (or press Enter to cancel): ").strip()
        if not raw:
            return None
        try:
            lat_str, lng_str = raw.split(",")
            return float(lat_str.strip()), float(lng_str.strip())
        except Exception:
            print("Invalid format. Please enter like: 1.3521, 103.8198")
            return None

    @staticmethod
    def get_coords(address_or_postal: str) -> Optional[Coord]:
        address_or_postal = (address_or_postal or "").strip()
        if not address_or_postal:
            return None
        if requests is None:
            return LocationPlanner._prompt_manual_coords(address_or_postal)
        try:
            url = (
                "https://www.onemap.gov.sg/api/common/elastic/search"
                f"?searchVal={address_or_postal}&returnGeom=Y&getAddrDetails=Y&pageNum=1"
            )
            resp = requests.get(url, timeout=8)
            data = resp.json()
            if data.get("found", 0) > 0 and data.get("results"):
                r0 = data["results"][0]
                return float(r0["LATITUDE"]), float(r0["LONGITUDE"])
            print(f"OneMap could not find: {address_or_postal}")
            return LocationPlanner._prompt_manual_coords(address_or_postal)
        except Exception as e:
            print(f"OneMap error: {e}")
            return LocationPlanner._prompt_manual_coords(address_or_postal)

    @staticmethod
    def _distance_km(start: Coord, end: Coord) -> float:
        if geodesic is not None:
            return float(geodesic(start, end).km)
        import math
        lat1, lon1 = start
        lat2, lon2 = end
        km_per_deg_lat = 111.0
        km_per_deg_lon = 111.0 * max(0.1, abs(math.cos(math.radians((lat1 + lat2) / 2))))
        return float((((lat2 - lat1) * km_per_deg_lat) ** 2 + ((lon2 - lon1) * km_per_deg_lon) ** 2) ** 0.5)

    @staticmethod
    def _route_walk_km_mins(start: Coord, end: Coord) -> Tuple[float, float]:
        if requests is not None:
            try:
                url = (
                    "https://www.onemap.gov.sg/api/public/routing/route"
                    f"?start={start[0]},{start[1]}&end={end[0]},{end[1]}&routeType=walk"
                )
                data = requests.get(url, timeout=8).json()
                summary = data.get("route_summary") or {}
                dist_km = float(summary.get("total_distance", 0)) / 1000.0
                time_mins = float(summary.get("total_time", 0)) / 60.0
                if dist_km > 0 and time_mins > 0:
                    return float(dist_km), float(time_mins)
            except Exception:
                pass
        dist_km = LocationPlanner._distance_km(start, end)
        return float(dist_km), float(dist_km * 12.0)

    def build_stall_itinerary(self, start_coords: Coord, stalls_df: pd.DataFrame, max_stops: int = 5):
        required = {"latitude_hc", "longitude_hc", "stall_name"}
        if stalls_df is None or stalls_df.empty or not required.issubset(set(stalls_df.columns)):
            return [], 0.0, 0.0
        route: List[Dict] = []
        remaining = stalls_df.copy().drop_duplicates(subset=["stall_id"]).head(max(5, max_stops))
        current = start_coords
        total_km = 0.0
        total_mins = 0.0
        while not remaining.empty and len(route) < max_stops:
            best_idx = None
            best_dist = float("inf")
            best_time = 0.0
            for idx, row in remaining.iterrows():
                end = (float(row["latitude_hc"]), float(row["longitude_hc"]))
                dist_km, time_mins = self._route_walk_km_mins(current, end)
                if dist_km < best_dist:
                    best_idx = idx
                    best_dist = dist_km
                    best_time = time_mins
            chosen = remaining.loc[best_idx].to_dict()
            chosen["leg_dist_km"] = best_dist
            chosen["leg_time_mins"] = best_time
            total_km += best_dist
            total_mins += best_time
            route.append(chosen)
            current = (float(chosen["latitude_hc"]), float(chosen["longitude_hc"]))
            remaining = remaining.drop(best_idx)
        return route, total_km, total_mins