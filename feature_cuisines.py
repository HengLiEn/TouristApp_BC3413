"""
Feature: Cuisine Preferences Module for TouristApp_BC3413
Author: LiEn
Project: Singapore Tourist App BC3407
"""

import pandas as pd
import os
from typing import List, Optional
from dataclasses import dataclass
import sqlite3

# Same DB as Saachee's main.py
DB_FILE = "tourist_profiles.db"


@dataclass
class CuisinePreferences:
    # reason of branching this to none instead of empty list such that it doesn't append to the same instance by accident.
    """User's cuisine preferences - ONLY food-related attributes"""
    cuisines: List[str] = None          # e.g., ['Chinese', 'Malay', 'Indian']
    dietary_restrictions: List[str] = None  # e.g., ['vegetarian', 'halal']
    allergens_to_avoid: List[str] = None    # e.g., ['Dairy', 'Nuts']

    def __post_init__(self):
        if self.cuisines is None:
            self.cuisines = []
        if self.dietary_restrictions is None:
            self.dietary_restrictions = []
        if self.allergens_to_avoid is None:
            self.allergens_to_avoid = []


class CuisineFeatureHandler:

    def __init__(self, project_root: str = None):
        self.project_root = project_root or os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(self.project_root, 'dataset', 'Multiple Stalls Menu and Data')

        self.menu_df = pd.read_csv(os.path.join(data_dir, 'menu_items.csv'))
        self.stalls_df = pd.read_csv(os.path.join(data_dir, 'stalls.csv'))
        self.merged_df = self.menu_df.merge(self.stalls_df, on='stall_id', how='left')
        print(f" Loaded {len(self.menu_df):,} items from {len(self.stalls_df):,} stalls")

    # return the list of cuisines available
    def get_available_cuisines(self) -> List[str]:
        return sorted(self.stalls_df['cuisine_type'].unique())

    def get_available_allergens(self) -> List[str]:
        all_allergens = set()
        for entry in self.menu_df['allergens'].dropna():
            # make sure it is a string and not 'none'
            if isinstance(entry, str) and entry.lower() != 'none':
                # split by comma and remove empty spaces using strip
                all_allergens.update(a.strip() for a in entry.split(','))
        return sorted(all_allergens)

    def filter(self, prefs: CuisinePreferences):
        df = self.merged_df.copy()

        if prefs.cuisines:
            df = df[df['cuisine_type'].str.lower().isin([c.lower() for c in prefs.cuisines])]

        dietary = [d.lower() for d in prefs.dietary_restrictions]
        if 'vegetarian' in dietary:
            df = df[df['vegetarian'] == 1]  # binary 0/1
        if 'halal' in dietary:
            df = df[df['halal'] == 1]  # binary 0/1

        for allergen in prefs.allergens_to_avoid:
            # remove rows that contain those allergens with ~
            df = df[~df['allergens'].str.contains(allergen, case=False, na=False)]

        df = df[df['is_available'] == True]
        print(f"{len(df):,} items match your preferences")
        return df

    # display function for a nicer presentation
    def display(self, df: pd.DataFrame, max_display: int = 20):
        if df.empty:
            print("No items found. Try adjusting your preferences.")
            return

        print(f"\n{'='*60}\n  {len(df):,} items found — showing {min(max_display, len(df))}\n{'='*60}\n")

        for i, (_, row) in enumerate(df.head(max_display).iterrows(), 1):
            tags = []
            if row['halal'] == 1: tags.append("Halal")
            if row['vegetarian'] == 1: tags.append("Veg")

            print(f"{i}. {row['item_name']} ({row['cuisine_type']})")
            print(f"   📍 {row['stall_name']}  ")
            if tags: print(f"   {' | '.join(tags)}")
            print()

        if len(df) > max_display:
            print(f"... and {len(df) - max_display:,} more. Export CSV using 'export' function.")

    # export filtered data to CSV
    def export(self, prefs: CuisinePreferences, filename: str = 'filtered_cuisine_data.csv'):
        df = self.filter(prefs)
        if df.empty:
            print("Nothing to export.")
            return df

        output_path = os.path.join(self.project_root, filename)
        df.to_csv(output_path, index=False)
        print(f" Saved {len(df):,} items to {output_path}")
        return df

    def save_preferences(self, prefs: CuisinePreferences, user_id: str):
        """
        Updates the tourist's cuisine preferences in tourist_profiles.db.
        Looks up the tourist by user_id (primary key) and updates their record.
        """
        try:
            with sqlite3.connect(DB_FILE) as con:
                con.execute("""
                            UPDATE tourist_profiles
                            SET preferred_cuisines = ?,
                                dietary            = ?,
                                allergens          = ?
                            WHERE user_id = ?
                            """, (
                                "|".join(prefs.cuisines),
                                "|".join(prefs.dietary_restrictions),
                                "|".join(prefs.allergens_to_avoid),
                                user_id
                            ))
                con.commit()
            print(f"Preferences updated in database for '{user_id}'.")
        except Exception as e:
            print(f"Error saving preferences: {e}")


    def load_preferences(self, user_id: str) -> Optional[CuisinePreferences]:
        """
        Loads cuisine preferences from tourist_profiles.db by user_id (primary key).
        Returns CuisinePreferences object or None if not found.
        """
        try:
            with sqlite3.connect(DB_FILE) as con:
                row = con.execute("""
                                  SELECT preferred_cuisines, dietary, allergens
                                  FROM tourist_profiles
                                  WHERE user_id = ?
                                  """, (user_id,)).fetchone()

            if not row:
                print(f"No profile found for '{user_id}'.")
                return None

            def unpack(s):
                return [x.strip() for x in s.split("|") if x.strip()] if s else []

            print(f"Loaded preferences for '{user_id}' from database.")
            return CuisinePreferences(
                cuisines=unpack(row[0]),
                dietary_restrictions=unpack(row[1]),
                allergens_to_avoid=unpack(row[2])
            )

        except Exception as e:
            print(f"Error loading preferences: {e}")
            return None


if __name__ == "__main__":
    handler = CuisineFeatureHandler()
    prefs = CuisinePreferences(cuisines=["Chinese"], dietary_restrictions=["halal"])
    df = handler.filter(prefs)
    handler.display(df)
