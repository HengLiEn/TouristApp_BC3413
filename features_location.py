"""
features_location.py
Location & Itinerary Planner — supports optional start_coords from main.py

Change:
- run_interactive(start_coords=None) added
  If start_coords provided, it skips asking the user for current location.
"""

from __future__ import annotations

import os
from datetime import datetime
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

        data_hc_dir = os.path.join(self.project_root, "dataset", "Hawker Centre Data")
        data_menu_dir = os.path.join(self.project_root, "dataset", "Multiple Stalls Menu and Data")

        self.hc_path = os.path.join(data_hc_dir, "DatesofHawkerCentresClosure.csv")
        self.stalls_path = os.path.join(data_menu_dir, "stalls.csv")
        self.menu_items_path = os.path.join(data_menu_dir, "menu_items.csv")

        try:
            self.hc_df = pd.read_csv(self.hc_path)
        except FileNotFoundError:
            print(f"Error: Hawker centre dataset not found at: {self.hc_path}")
            self.hc_df = pd.DataFrame()

        try:
            self.stalls_df = pd.read_csv(self.stalls_path)
        except FileNotFoundError:
            print(f"Error: stalls.csv not found at: {self.stalls_path}")
            self.stalls_df = pd.DataFrame()

        if os.path.exists(self.menu_items_path):
            try:
                self.menu_df = pd.read_csv(self.menu_items_path)
            except Exception:
                self.menu_df = pd.DataFrame()
        else:
            self.menu_df = pd.DataFrame()

        self.merged_stalls = pd.DataFrame()
        if not self.hc_df.empty and not self.stalls_df.empty:
            if "hawker_center_id" in self.stalls_df.columns and "serial_no" in self.hc_df.columns:
                self.merged_stalls = pd.merge(
                    self.stalls_df,
                    self.hc_df,
                    left_on="hawker_center_id",
                    right_on="serial_no",
                    how="inner",
                )

        self.merged_menu = pd.DataFrame()
        if not self.menu_df.empty and not self.merged_stalls.empty:
            if "stall_id" in self.menu_df.columns and "stall_id" in self.merged_stalls.columns:
                self.merged_menu = pd.merge(self.menu_df, self.merged_stalls, on="stall_id", how="inner")

    # -----------------------------
    # Coordinate helpers
    # -----------------------------
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
            print("\n⚠️ 'requests' not installed → cannot use OneMap lookup.")
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

    # -----------------------------
    # Route planning
    # -----------------------------
    def calculate_best_route(self, start_coords: Coord, stops_df: pd.DataFrame) -> Tuple[List[Dict], float, float]:
        required = {"latitude_hc", "longitude_hc", "name"}
        if stops_df is None or stops_df.empty or not required.issubset(set(stops_df.columns)):
            return [], 0.0, 0.0

        route: List[Dict] = []
        remaining = stops_df.copy()
        current = start_coords
        total_km = 0.0
        total_mins = 0.0

        while not remaining.empty:
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

    # -----------------------------
    # Interactive runner
    # -----------------------------
    def run_interactive(self, start_coords: Optional[Coord] = None) -> None:
        if self.hc_df.empty:
            print("Location planner cannot run because hawker centre dataset is missing.")
            return

        print("\n=== Location & Itinerary Planner ===")
        if requests is None:
            print("Note: OneMap geocoding/routing disabled (install 'requests' for auto lookup).")

        # 1) Start location
        if start_coords is None:
            while True:
                user_addr = input("Enter your current location (postal/address, e.g. 'Bedok' or '570235'): ").strip()
                start_coords = self.get_coords(user_addr)
                if start_coords:
                    print("Location recognized!\n")
                    break
                print("Could not set your location. Try again.\n")
        else:
            print(f"Using saved start location: ({start_coords[0]:.6f}, {start_coords[1]:.6f})")

        # 2) Date
        while True:
            date_input = input("Enter the date (YYYY-MM-DD): ").strip()
            try:
                datetime.strptime(date_input, "%Y-%m-%d")
                explore_date = date_input
                break
            except ValueError:
                print("Invalid format. Use YYYY-MM-DD (e.g., 2026-03-05).")

        # 3) Select stops (simple hawker centre name search)
        selected_rows: List[Dict] = []

        while len(selected_rows) < 5:
            print(f"\n--- Itinerary for {explore_date} (Stops: {len(selected_rows)}/5) ---")
            print("[1] Search Hawker Centre Name  [done] Finish Selection")
            mode = input("Option: ").strip().lower()

            if mode == "done":
                if selected_rows:
                    break
                print("Pick at least one stop.")
                continue

            if mode != "1":
                print("Invalid option.")
                continue

            query = input("Enter hawker centre name keyword (e.g. 'Maxwell', 'Old Airport'): ").strip()
            if not query:
                continue

            matches = self.hc_df[self.hc_df["name"].astype(str).str.contains(query, case=False, na=False)]
            if matches.empty:
                print("No hawker centres matched that keyword.")
                continue

            show = matches.head(15).reset_index(drop=True)
            for i, row in show.iterrows():
                print(f"[{i + 1}] {row.get('name', 'Unknown')}")

            raw = input("Enter choice number(s), comma-separated: ").strip()
            if not raw:
                continue

            try:
                picks = [int(x.strip()) - 1 for x in raw.split(",")]
                for p in picks:
                    if 0 <= p < len(show):
                        selected_rows.append(show.iloc[p].to_dict())
                        print(f"Added: {show.iloc[p].get('name', 'Unknown')}")
            except Exception:
                print("Invalid selection.")

        selected_df = pd.DataFrame(selected_rows)
        if "serial_no" in selected_df.columns:
            selected_df = selected_df.drop_duplicates(subset=["serial_no"])

        itinerary, total_km, total_mins = self.calculate_best_route(start_coords, selected_df)

        if not itinerary:
            print("Could not compute itinerary (check that dataset has latitude_hc/longitude_hc).")
            return

        print("\n" + "═" * 60)
        print(f"ITINERARY FOR: {explore_date}")
        print("═" * 60)

        for i, hc in enumerate(itinerary, 1):
            travel_info = "STARTING POINT" if i == 1 else f"🚶 Travel: {hc['leg_dist_km']:.2f} km (~{round(hc['leg_time_mins'])} mins)"
            print(f"\n📍 STOP {i}: {hc.get('name', 'Unknown')}")
            print(f"   {travel_info}")

        print("\n" + "-" * 60)
        print(f"Total walking distance: {total_km:.2f} km")
        print(f"Estimated total walking time: {round(total_mins)} mins")
        print("-" * 60)


if __name__ == "__main__":
    LocationPlanner().run_interactive()