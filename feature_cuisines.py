"""
feature_cuisines.py — dietary removed

Changes:
- CuisinePreferences no longer has dietary_restrictions
- filter() no longer checks vegetarian/halal/vegan columns
- save_preferences/load_preferences no longer writes/reads dietary
"""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

DB_FILE = "tourist_profiles.db"


@dataclass
class CuisinePreferences:
    cuisines: List[str] = None
    allergens_to_avoid: List[str] = None

    def __post_init__(self):
        if self.cuisines is None:
            self.cuisines = []
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

    @staticmethod
    def _norm(s: str) -> str:
        return str(s).strip().lower()

    @staticmethod
    def _split_cell(cell: str) -> List[str]:
        if cell is None or (isinstance(cell, float) and pd.isna(cell)):
            return []
        text = str(cell).strip().lower()
        if not text or text == "nan":
            return []
        parts = re.split(r"[,\;/\|]+", text)
        return [p.strip() for p in parts if p.strip()]

    def get_available_cuisines(self) -> List[str]:
        if "cuisine_type" not in self.stalls_df.columns:
            return []
        vals = self.stalls_df["cuisine_type"].dropna().astype(str).tolist()
        tokens = set()
        for v in vals:
            for t in self._split_cell(v):
                tokens.add(t.title())
        return sorted(tokens)

    def get_available_allergens(self) -> List[str]:
        all_allergens = set()
        if "allergens" not in self.menu_df.columns:
            return []
        for entry in self.menu_df["allergens"].dropna():
            if isinstance(entry, str) and entry.strip() and entry.lower() != "none":
                all_allergens.update(a.strip() for a in entry.split(",") if a.strip())
        return sorted(all_allergens)

    @staticmethod
    def _apply_availability_filter_if_possible(df: pd.DataFrame) -> pd.DataFrame:
        if "is_available" not in df.columns:
            return df
        col = df["is_available"]

        # numeric 0/1
        if pd.api.types.is_numeric_dtype(col):
            uniques = set(pd.to_numeric(col, errors="coerce").dropna().unique().tolist())
            if uniques.issubset({0, 1}) and 1 in uniques:
                return df[pd.to_numeric(col, errors="coerce") == 1]
            return df

        # string yes/no style
        sample = col.dropna().astype(str).str.strip().str.lower()
        if sample.empty:
            return df
        uniques = set(sample.unique().tolist())
        truthy = {"y", "yes", "true", "t", "1", "available", "open"}
        falsy = {"n", "no", "false", "f", "0", "unavailable", "closed"}
        if uniques.issubset(truthy.union(falsy)):
            return df[sample.isin(truthy).reindex(df.index, fill_value=False)]

        return df

    def filter(self, prefs: CuisinePreferences) -> pd.DataFrame:
        df = self.merged_df.copy()

        # Cuisine filter
        if prefs.cuisines and "cuisine_type" in df.columns:
            wanted = [self._norm(c) for c in prefs.cuisines if str(c).strip()]

            def match_cell(cell: str) -> bool:
                tokens = self._split_cell(cell)
                return any(w in tokens for w in wanted) or any(w in str(cell).lower() for w in wanted)

            df = df[df["cuisine_type"].apply(match_cell)]

        # Allergens
        if prefs.allergens_to_avoid and "allergens" in df.columns:
            for allergen in prefs.allergens_to_avoid:
                a = str(allergen).strip()
                if a:
                    df = df[~df["allergens"].astype(str).str.contains(a, case=False, na=False)]

        # Availability (safe)
        df = self._apply_availability_filter_if_possible(df)

        print(f"{len(df):,} items match your preferences")
        return df

    def display(self, df: pd.DataFrame, max_display: int = 20) -> None:
        if df is None or df.empty:
            print("No items found. Try adjusting your preferences.")
            return

        print(f"\n{'=' * 60}\n  {len(df):,} items found — showing {min(max_display, len(df))}\n{'=' * 60}\n")

        for i, (_, row) in enumerate(df.head(max_display).iterrows(), 1):
            item = row.get("item_name", "Unknown item")
            cuisine = row.get("cuisine_type", "Unknown cuisine")
            stall = row.get("stall_name", "Unknown stall")
            price = row.get("price", None)

            print(f"{i}. {item} ({cuisine})")
            print(f"   📍 {stall}")
            if price is not None and str(price) != "nan":
                print(f"   💲 {price}")
            print()

        if len(df) > max_display:
            print(f"... and {len(df) - max_display:,} more.")

    # -----------------------------
    # DB integration (username PK) — dietary removed
    # -----------------------------
    def save_preferences(self, prefs: CuisinePreferences, username: str) -> None:
        try:
            with sqlite3.connect(DB_FILE) as con:
                con.execute(
                    """
                    UPDATE tourist_profiles
                    SET preferred_cuisines = ?,
                        allergens          = ?
                    WHERE username = ?;
                    """,
                    (
                        "|".join([str(x).strip() for x in prefs.cuisines if str(x).strip()]),
                        "|".join([str(x).strip() for x in prefs.allergens_to_avoid if str(x).strip()]),
                        username,
                    ),
                )
                con.commit()
            print(f"Preferences updated for '{username}'.")
        except Exception as e:
            print(f"Error saving preferences: {e}")

    def load_preferences(self, username: str) -> Optional[CuisinePreferences]:
        try:
            with sqlite3.connect(DB_FILE) as con:
                row = con.execute(
                    """
                    SELECT preferred_cuisines, allergens
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
                allergens_to_avoid=unpack(row[1]),
            )

        except Exception as e:
            print(f"Error loading preferences: {e}")
            return None