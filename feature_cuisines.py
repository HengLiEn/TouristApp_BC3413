"""
Feature: Cuisine Preferences Module for TouristApp_BC3413
Author: LiEn
Project: Singapore Tourist App BC3413
"""

import pandas as pd
import os
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class CuisinePreferences:
    #reason of branching this to none instead of empty list such that it doesn append to the same instance by accident.
    """User's cuisine preferences - ONLY food-related attributes"""
    cuisines: List[str] = None  # e.g., ['Chinese', 'Malay', 'Indian']
    dietary_restrictions: List[str] = None  # e.g., ['vegetarian', 'halal']
    allergens_to_avoid: List[str] = None  # e.g., ['Dairy', 'Nuts']

    def __post_init__(self):
        if self.cuisines is None:
            self.cuisines = []
        if self.dietary_restrictions is None:
            self.dietary_restrictions = []
        if self.allergens_to_avoid is None:
            self.allergens_to_avoid = []

class CuisineFeatureHandler:
    #return the list of cuisines available
    def get_available_cuisines(self) -> List[str]:
        return sorted(self.stalls_df['cuisine_type'].unique())

#display function for a nicer presentation
def display(df: pd.DataFrame, max_display: int = 20):
    if df.empty:
        print("No items found. Try adjusting your preferences.")
        return

    print(f"\n{'=' * 60}\n🍽️  {len(df):,} items found — showing {min(max_display, len(df))}\n{'=' * 60}\n")

    for i, (_, row) in enumerate(df.head(max_display).iterrows(), 1):
        tags = []
        if row['vegetarian'] == 'Yes': tags.append("Veg")
        if row['halal'] == 'Yes': tags.append("Halal")

        print(f"{i}. {row['item_name']} ({row['cuisine_type']})")
        print(f"   📍 {row['stall_name']}  💰 ${row['price']:.2f} ")
        if tags: print(f"   {' | '.join(tags)}")
        print()

    if len(df) > max_display:
        print(f"... and {len(df) - max_display:,} more. Export CSV using 'export' function.")

#function created on an exportion where the filtered data based on user choose is exported out to csv for easier ereference
def export(self, prefs: CuisinePreferences, filename: str = 'filtered_cuisine_data.csv') -> pd.DataFrame:
    df = self.filter(prefs)
    if df.empty:
        print(" Nothing to export.")
        return df

    output_path = os.path.join(self.project_root, filename)
    df.to_csv(output_path, index=False)
    print(f" Saved {len(df):,} items to {output_path}")
    return df

if __name__ == "__main__":
    # Run interactive mode when executed directly
    interactive_cuisine_selector()
