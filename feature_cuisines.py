"""
Feature: Cuisine Preferences Module for TouristApp_BC3413
Author: LiEn
Project: Singapore Tourist App BC3413

This module:
- Loads menu_items.csv and stalls.csv
- Lets users filter menu items based on cuisine/dietary/allergen preferences
- Saves/loads preferences into tourist_profiles.db (table: tourist_profiles)

IMPORTANT (integration):
- We use `username` as the primary key (matches saachees_file.py)
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

DB_FILE = "tourist_profiles.db"


@dataclass
class CuisinePreferences:
    """User's cuisine preferences (food-related attributes)."""
    cuisines: List[str] = None
    dietary_restrictions: List[str] = None
    allergens_to_avoid: List[str] = None

    def __post_init__(self):
        # Avoid mutable default list bugs
        if self.cuisines is None:
            self.cuisines = []
        if self.dietary_restrictions is None:
            self.dietary_restrictions = []
        if self.allergens_to_avoid is None:
            self.allergens_to_avoid = []


class CuisineFeatureHandler:
    def __init__(self, project_root: str = None):
        self.project_root = project_root or os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(self.project_root, "dataset", "Multiple Stalls Menu and Data")

        self.menu_df = pd.read_csv(os.path.join(data_dir, "menu_items.csv"))
        self.stalls_df = pd.read_csv(os.path.join(data_dir, "stalls.csv"))
        self.merged_df = self.menu_df.merge(self.stalls_df, on="stall_id", how="left")

        print(f"Loaded {len(self.menu_df):,} items from {len(self.stalls_df):,} stalls")

    def get_available_cuisines(self) -> List[str]:
        return sorted(self.stalls_df["cuisine_type"].dropna().unique())

    def get_available_allergens(self) -> List[str]:
        all_allergens = set()
        if "allergens" not in self.menu_df.columns:
            return []

        for entry in self.menu_df["allergens"].dropna():
            if isinstance(entry, str) and entry.strip() and entry.lower() != "none":
                all_allergens.update(a.strip() for a in entry.split(",") if a.strip())
        return sorted(all_allergens)

    def filter(self, prefs: CuisinePreferences) -> pd.DataFrame:
        df = self.merged_df.copy()

        # Cuisine type
        if prefs.cuisines and "cuisine_type" in df.columns:
            df = df[df["cuisine_type"].astype(str).str.lower().isin([c.lower() for c in prefs.cuisines])]

        # Dietary
        dietary = [d.lower() for d in prefs.dietary_restrictions]
        if "vegetarian" in dietary and "vegetarian" in df.columns:
            df = df[df["vegetarian"] == 1]
        if "halal" in dietary and "halal" in df.columns:
            df = df[df["halal"] == 1]

        # Allergens
        if "allergens" in df.columns:
            for allergen in prefs.allergens_to_avoid:
                df = df[~df["allergens"].astype(str).str.contains(allergen, case=False, na=False)]

        # Availability (if present)
        if "is_available" in df.columns:
            df = df[df["is_available"] == True]

        print(f"{len(df):,} items match your preferences")
        return df

    def display(self, df: pd.DataFrame, max_display: int = 20) -> None:
        if df is None or df.empty:
            print("No items found. Try adjusting your preferences.")
            return

        print(f"\n{'=' * 60}\n  {len(df):,} items found — showing {min(max_display, len(df))}\n{'=' * 60}\n")

        for i, (_, row) in enumerate(df.head(max_display).iterrows(), 1):
            tags = []
            if "halal" in row and row.get("halal", 0) == 1:
                tags.append("Halal")
            if "vegetarian" in row and row.get("vegetarian", 0) == 1:
                tags.append("Veg")

            item = row.get("item_name", "Unknown item")
            cuisine = row.get("cuisine_type", "Unknown cuisine")
            stall = row.get("stall_name", "Unknown stall")

            print(f"{i}. {item} ({cuisine})")
            print(f"   📍 {stall}")
            if tags:
                print(f"   {' | '.join(tags)}")
            print()

        if len(df) > max_display:
            print(f"... and {len(df) - max_display:,} more.")

    def export(self, prefs: CuisinePreferences, filename: str = "filtered_cuisine_data.csv") -> pd.DataFrame:
        df = self.filter(prefs)
        if df.empty:
            print("Nothing to export.")
            return df

        output_path = os.path.join(self.project_root, filename)
        df.to_csv(output_path, index=False)
        print(f"Saved {len(df):,} items to {output_path}")
        return df

    # -----------------------------
    # DB integration (username PK)
    # -----------------------------
    def save_preferences(self, prefs: CuisinePreferences, username: str) -> None:
        """
        Updates cuisine-related preferences in tourist_profiles.db for the given username.
        """
        try:
            with sqlite3.connect(DB_FILE) as con:
                con.execute(
                    """
                    UPDATE tourist_profiles
                    SET preferred_cuisines = ?,
                        dietary            = ?,
                        allergens          = ?
                    WHERE username = ?;
                    """,
                    (
                        "|".join(prefs.cuisines),
                        "|".join(prefs.dietary_restrictions),
                        "|".join(prefs.allergens_to_avoid),
                        username,
                    ),
                )
                con.commit()
            print(f"Preferences updated for '{username}'.")
        except Exception as e:
            print(f"Error saving preferences: {e}")

    def load_preferences(self, username: str) -> Optional[CuisinePreferences]:
        """
        Loads cuisine-related preferences from tourist_profiles.db for the given username.
        """
        try:
            with sqlite3.connect(DB_FILE) as con:
                row = con.execute(
                    """
                    SELECT preferred_cuisines, dietary, allergens
                    FROM tourist_profiles
                    WHERE username = ?;
                    """,
                    (username,),
                ).fetchone()

            if not row:
                return None

            def unpack(s: Optional[str]) -> List[str]:
                return [x.strip() for x in str(s).split("|") if x.strip()] if s else []

            return CuisinePreferences(
                cuisines=unpack(row[0]),
                dietary_restrictions=unpack(row[1]),
                allergens_to_avoid=unpack(row[2]),
            )

        except Exception as e:
            print(f"Error loading preferences: {e}")
            return None


if __name__ == "__main__":
    handler = CuisineFeatureHandler()
    prefs = CuisinePreferences(cuisines=["Chinese"], dietary_restrictions=["halal"])
    df = handler.filter(prefs)
    handler.display(df)