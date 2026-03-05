"""
Feature: Location & Itinerary Planner for TouristApp_BC3413
Author: Nicole (refactored for importability)

Key changes for integration:
- No code runs on import (everything is behind class methods / __main__)
- Fixes previous script-level references (df/get_coords/merged_stalls) by using self.*
- Provides `run_interactive()` so main.py can call it cleanly

Notes:
- Uses OneMap Search API to geocode user input.
- Uses OneMap Routing API (walking) when available; falls back to geodesic distance.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
from geopy.distance import geodesic


Coord = Tuple[float, float]


class LocationPlanner:
    def __init__(self, project_root: str = None):
        self.project_root = project_root or os.path.dirname(os.path.abspath(__file__))

        # Load datasets
        hc_path = os.path.join(self.project_root, "dataset", "Hawker Centre Data", "DatesofHawkerCentresClosure.csv")
        stalls_path = os.path.join(self.project_root, "dataset", "Multiple Stalls Menu and Data", "stalls.csv")

        try:
            self.hc_df = pd.read_csv(hc_path)
        except FileNotFoundError:
            print(f"Error: Hawker closure dataset not found at: {hc_path}")
            self.hc_df = pd.DataFrame()

        try:
            self.stalls_df = pd.read_csv(stalls_path)
        except FileNotFoundError:
            print(f"Warning: stalls.csv not found at: {stalls_path}")
            self.stalls_df = pd.DataFrame()

        # Attempt to merge stalls -> hawker centre info if keys exist
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

    # -----------------------------
    # OneMap helpers
    # -----------------------------
    @staticmethod
    def get_coords(address_or_postal: str) -> Optional[Coord]:
        """
        Uses OneMap API to turn SG address/postal code into coordinates.
        """
        address_or_postal = (address_or_postal or "").strip()
        if not address_or_postal:
            return None

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
            return None
        except Exception as e:
            print(f"Connection error (OneMap search): {e}")
            return None

    @staticmethod
    def _route_walk_km_mins(start: Coord, end: Coord) -> Tuple[float, float]:
        """
        Returns (distance_km, time_minutes) using OneMap routing if possible.
        Falls back to geodesic distance and a rough walking pace (12 mins/km).
        """
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
                return dist_km, time_mins
        except Exception:
            pass

        # fallback
        dist_km = geodesic(start, end).km
        time_mins = dist_km * 12.0
        return float(dist_km), float(time_mins)

    # -----------------------------
    # Route planning
    # -----------------------------
    def calculate_best_route(self, start_coords: Coord, stops_df: pd.DataFrame) -> Tuple[List[Dict], float, float]:
        """
        Greedy nearest-next routing by walking distance.
        Expects stops_df contains columns:
          - name (hawker name)
          - latitude_hc
          - longitude_hc
        """
        required = {"latitude_hc", "longitude_hc"}
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
    def run_interactive(self) -> None:
        if self.hc_df.empty:
            print("Location planner cannot run because hawker centre dataset is missing.")
            return

        print("\n--- Advanced Hawker Centre & Stall Itinerary Planner ---")

        # 1) Get user start location
        while True:
            user_addr = input("Enter your current location (e.g. 'Bedok' or '639798'): ").strip()
            user_coords = self.get_coords(user_addr)
            if user_coords:
                print("Location recognized!")
                break
            print("Location not found. Try again.")

        # 2) Validate date (currently used as a label; closure filtering can be added later)
        while True:
            date_input = input("\nEnter the date (YYYY-MM-DD): ").strip()
            try:
                datetime.strptime(date_input, "%Y-%m-%d")
                explore_date = date_input
                break
            except ValueError:
                print("Invalid format! Please use YYYY-MM-DD (e.g., 2026-08-09).")

        # 3) Select up to 5 stops
        selected_rows: List[Dict] = []

        while len(selected_rows) < 5:
            print(f"\n--- Itinerary for {explore_date} (Stops: {len(selected_rows)}/5) ---")
            print("[1] Search Hawker Centre Name  [2] Search Stall Name  [done] Finish Selection")
            mode = input("Option: ").strip().lower()

            if mode == "done":
                if selected_rows:
                    break
                print("Pick at least one stop.")
                continue

            query = input("Enter search term: ").strip()
            if not query:
                continue

            matches = pd.DataFrame()

            if mode == "1":
                if "name" not in self.hc_df.columns:
                    print("Dataset missing 'name' column for hawker centres.")
                    continue
                matches = self.hc_df[self.hc_df["name"].astype(str).str.contains(query, case=False, na=False)]

            elif mode == "2":
                if self.merged_stalls.empty or "stall_name" not in self.merged_stalls.columns:
                    print("Stall search not available (stalls dataset missing).")
                    continue
                matches = self.merged_stalls[self.merged_stalls["stall_name"].astype(str).str.contains(query, case=False, na=False)]

                # If too many matches, prompt user to pick hawker centre
                if len(matches) > 10 and "name" in matches.columns:
                    print(f"Found {len(matches)} stalls. Filter by hawker centre:")
                    locs = list(matches["name"].dropna().unique())
                    for i, l in enumerate(locs, 1):
                        print(f"{i}. {l}")
                    pick = input("Choose hawker centre number (or press Enter to skip): ").strip()
                    if pick.isdigit():
                        idx = int(pick) - 1
                        if 0 <= idx < len(locs):
                            matches = matches[matches["name"] == locs[idx]]

                # Keep only hawker-centre-level columns for routing
                if not matches.empty and "serial_no" in matches.columns:
                    matches = matches.drop_duplicates(subset=["serial_no"])

            else:
                print("Invalid option.")
                continue

            if matches.empty:
                print("No results.")
                continue

            # Display up to 15 results
            show_df = matches.head(15).reset_index(drop=True)
            for i, row in show_df.iterrows():
                if mode == "1":
                    print(f"[{i + 1}] {row.get('name', 'Unknown')}")
                else:
                    print(f"[{i + 1}] {row.get('stall_name', 'Unknown')} ({row.get('name', 'Unknown')})")

            choice = input("Enter choice number(s), comma-separated: ").strip()
            if not choice:
                continue

            try:
                picks = [int(x.strip()) - 1 for x in choice.split(",")]
                for p in picks:
                    if 0 <= p < len(show_df):
                        selected_rows.append(show_df.iloc[p].to_dict())
                        print(f"Added: {show_df.iloc[p].get('name', 'Unknown')}")
            except Exception:
                print("Invalid selection.")

        # Build dataframe of selected hawker centres (unique)
        selected_df = pd.DataFrame(selected_rows)
        if "serial_no" in selected_df.columns:
            selected_df = selected_df.drop_duplicates(subset=["serial_no"])

        itinerary, total_km, total_mins = self.calculate_best_route(user_coords, selected_df)

        if not itinerary:
            print("No itinerary created.")
            return

        print("\n" + "═" * 60)
        print(f"SAVED ITINERARY FOR: {explore_date}")
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