"""
feature_cuisines.py — stall-first, location-aware, bayes-ranked recommendations (no startup prints)
"""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pandas as pd

DB_FILE = "tourist_profiles.db"
Coord = Tuple[float, float]


@dataclass
class CuisinePreferences:
    cuisines: List[str] = None
    allergens_to_avoid: List[str] = None

    def __post_init__(self):
        self.cuisines = self.cuisines or []
        self.allergens_to_avoid = self.allergens_to_avoid or []


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class CuisineFeatureHandler:
    def __init__(self, project_root: str = None):
        self.project_root = project_root or os.path.dirname(os.path.abspath(__file__))

        menu_dir = os.path.join(self.project_root, "dataset", "Multiple Stalls Menu and Data")
        hc_dir = os.path.join(self.project_root, "dataset", "Hawker Centre Data")

        self.menu_path = os.path.join(menu_dir, "menu_items.csv")
        self.stalls_path = os.path.join(menu_dir, "stalls.csv")
        self.reviews_path = os.path.join(menu_dir, "reviews.csv")
        self.hc_path = os.path.join(hc_dir, "DatesofHawkerCentresClosure.csv")

        self.menu_df = pd.read_csv(self.menu_path)
        self.stalls_df = pd.read_csv(self.stalls_path)
        self.hc_df = pd.read_csv(self.hc_path)

        df = self.menu_df.merge(self.stalls_df, on="stall_id", how="left")

        if "hawker_center_id" in df.columns and "serial_no" in self.hc_df.columns:
            df = df.merge(
                self.hc_df[["serial_no", "name", "latitude_hc", "longitude_hc"]],
                left_on="hawker_center_id",
                right_on="serial_no",
                how="left",
            ).rename(columns={"name": "hawker_name"})

        self.merged_df = df

        self._reviews_df: Optional[pd.DataFrame] = None
        self._bayes_scores: Optional[pd.DataFrame] = None

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

            def unpack(s):
                return [x.strip() for x in str(s).split("|") if x.strip()] if s else []

            return CuisinePreferences(
                cuisines=unpack(row[0]),
                allergens_to_avoid=unpack(row[1]),
            )
        except Exception as e:
            print(f"Error loading preferences: {e}")
            return None

    def _filter_items_by_prefs(self, prefs: CuisinePreferences) -> pd.DataFrame:
        df = self.merged_df.copy()

        if prefs.cuisines and "cuisine_type" in df.columns:
            wanted = [self._norm(c) for c in prefs.cuisines if str(c).strip()]

            def match_cell(cell: str) -> bool:
                tokens = self._split_cell(cell)
                return any(w in tokens for w in wanted) or any(w in str(cell).lower() for w in wanted)

            df = df[df["cuisine_type"].apply(match_cell)]

        if prefs.allergens_to_avoid and "allergens" in df.columns:
            for allergen in prefs.allergens_to_avoid:
                a = str(allergen).strip()
                if a:
                    df = df[~df["allergens"].astype(str).str.contains(a, case=False, na=False)]

        return df

    def _apply_location_filter(self, df: pd.DataFrame, coords: Optional[Coord], radius_km: float) -> pd.DataFrame:
        if coords is None:
            return df
        if not {"latitude_hc", "longitude_hc"}.issubset(df.columns):
            return df

        lat0, lon0 = coords
        lat = pd.to_numeric(df["latitude_hc"], errors="coerce")
        lon = pd.to_numeric(df["longitude_hc"], errors="coerce")

        dist = []
        for a, b in zip(lat.tolist(), lon.tolist()):
            if a is None or b is None or pd.isna(a) or pd.isna(b):
                dist.append(float("inf"))
            else:
                dist.append(haversine_km(lat0, lon0, float(a), float(b)))

        out = df.copy()
        out["distance_km"] = dist
        out = out[out["distance_km"] <= float(radius_km)]
        return out

    def _load_reviews_if_needed(self) -> None:
        if self._reviews_df is not None:
            return
        self._reviews_df = pd.read_csv(self.reviews_path)
        if "rating" in self._reviews_df.columns:
            self._reviews_df["rating"] = pd.to_numeric(self._reviews_df["rating"], errors="coerce").fillna(0.0)
        else:
            self._reviews_df["rating"] = 0.0

    def compute_bayes_scores(self, m: float = 20.0) -> pd.DataFrame:
        if self._bayes_scores is not None:
            return self._bayes_scores

        self._load_reviews_if_needed()
        r = self._reviews_df

        if "stall_id" not in r.columns:
            self._bayes_scores = pd.DataFrame(columns=["stall_id", "avg_rating", "n_reviews", "bayes_score"])
            return self._bayes_scores

        C = float(r["rating"].mean()) if len(r) else 0.0

        agg = r.groupby("stall_id", as_index=False).agg(
            n_reviews=("rating", "count"),
            avg_rating=("rating", "mean"),
        )
        agg["bayes_score"] = (m * C + agg["n_reviews"] * agg["avg_rating"]) / (m + agg["n_reviews"])

        agg["avg_rating"] = agg["avg_rating"].round(2)
        agg["bayes_score"] = agg["bayes_score"].round(4)

        self._bayes_scores = agg[["stall_id", "avg_rating", "n_reviews", "bayes_score"]]
        return self._bayes_scores

    def get_top_nearby_stalls(
        self,
        prefs: CuisinePreferences,
        coords: Optional[Coord],
        radius_km: float,
        top_n: int = 5,
        m: float = 20.0,
    ) -> pd.DataFrame:
        items = self._filter_items_by_prefs(prefs)
        items = self._apply_location_filter(items, coords=coords, radius_km=radius_km)

        if items.empty:
            return pd.DataFrame()

        stall_cols = ["stall_id", "stall_name", "hawker_name", "latitude_hc", "longitude_hc"]
        if "distance_km" in items.columns:
            stall_cols.append("distance_km")

        stalls = items[stall_cols].drop_duplicates(subset=["stall_id"]).copy()
        if "distance_km" not in stalls.columns:
            stalls["distance_km"] = float("nan")

        scores = self.compute_bayes_scores(m=m)
        stalls["stall_id"] = pd.to_numeric(stalls["stall_id"], errors="coerce")
        scores["stall_id"] = pd.to_numeric(scores["stall_id"], errors="coerce")

        out = stalls.merge(scores, on="stall_id", how="left")
        out["n_reviews"] = out["n_reviews"].fillna(0).astype(int)
        out["avg_rating"] = out["avg_rating"].fillna(0.0)
        out["bayes_score"] = out["bayes_score"].fillna(0.0)

        out = out.sort_values(
            ["bayes_score", "avg_rating", "n_reviews", "distance_km"],
            ascending=[False, False, False, True],
        )

        return out.head(int(top_n)).reset_index(drop=True)

    def get_menu_for_stall(self, stall_id: int, prefs: CuisinePreferences) -> pd.DataFrame:
        df = self.merged_df.copy()
        df["stall_id"] = pd.to_numeric(df["stall_id"], errors="coerce")
        df = df[df["stall_id"] == int(stall_id)].copy()

        if prefs.allergens_to_avoid and "allergens" in df.columns:
            for allergen in prefs.allergens_to_avoid:
                a = str(allergen).strip()
                if a:
                    df = df[~df["allergens"].astype(str).str.contains(a, case=False, na=False)]

        keep = [c for c in ["item_name", "price", "stall_name", "hawker_name"] if c in df.columns]
        df = df[keep].copy()

        if "price" in df.columns:
            df["price"] = pd.to_numeric(df["price"], errors="coerce")
            df = df.sort_values(["price", "item_name"], ascending=[True, True])
        else:
            df = df.sort_values(["item_name"], ascending=True)

        return df.reset_index(drop=True)