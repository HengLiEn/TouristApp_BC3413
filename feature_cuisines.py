from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pandas as pd

from features_closure import HawkerClosureFeature

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
            keep = [c for c in ["serial_no", "name", "latitude_hc", "longitude_hc"] if c in self.hc_df.columns]
            df = df.merge(self.hc_df[keep], left_on="hawker_center_id", right_on="serial_no", how="left")
            if "name" in df.columns:
                df = df.rename(columns={"name": "hawker_name"})
        self.merged_df = df
        self._reviews_df: Optional[pd.DataFrame] = None
        self._bayes_scores: Optional[pd.DataFrame] = None
        self.closure = HawkerClosureFeature(project_root=self.project_root)

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
        tokens = set()
        for v in self.stalls_df["cuisine_type"].dropna().astype(str):
            for t in self._split_cell(v):
                tokens.add(t.title())
        return sorted(tokens)

    def save_preferences(self, prefs: CuisinePreferences, username: str) -> None:
        with sqlite3.connect(DB_FILE) as con:
            con.execute(
                "UPDATE tourist_profiles SET preferred_cuisines = ?, allergens = ? WHERE username = ?;",
                (
                    "|".join([str(x).strip() for x in prefs.cuisines if str(x).strip()]),
                    "|".join([str(x).strip() for x in prefs.allergens_to_avoid if str(x).strip()]),
                    username,
                ),
            )
            con.commit()

    def load_preferences(self, username: str) -> Optional[CuisinePreferences]:
        try:
            with sqlite3.connect(DB_FILE) as con:
                row = con.execute(
                    "SELECT preferred_cuisines, allergens FROM tourist_profiles WHERE username = ?;",
                    (username,),
                ).fetchone()
            if not row:
                return None
            def unpack(s):
                return [x.strip() for x in str(s).split("|") if x.strip()] if s else []
            return CuisinePreferences(cuisines=unpack(row[0]), allergens_to_avoid=unpack(row[1]))
        except Exception:
            return None

    def _get_reviews_df(self) -> pd.DataFrame:
        if self._reviews_df is None:
            df = pd.read_csv(self.reviews_path)
            if "rating" not in df.columns:
                df["rating"] = 0
            df["rating"] = pd.to_numeric(df["rating"], errors="coerce").fillna(0.0)
            self._reviews_df = df
        return self._reviews_df

    def _get_bayes_scores(self, m: float = 20.0) -> pd.DataFrame:
        if self._bayes_scores is not None:
            return self._bayes_scores
        reviews = self._get_reviews_df()
        global_mean = reviews["rating"].mean() if len(reviews) else 0.0
        agg = reviews.groupby("stall_id", as_index=False).agg(
            n_reviews=("rating", "count"),
            avg_rating=("rating", "mean"),
        )
        agg["bayes_score"] = (m * global_mean + agg["n_reviews"] * agg["avg_rating"]) / (m + agg["n_reviews"])
        self._bayes_scores = agg
        return agg

    def _apply_pref_filters(self, df: pd.DataFrame, prefs: CuisinePreferences) -> pd.DataFrame:
        out = df.copy()
        if prefs.cuisines and "cuisine_type" in out.columns:
            wanted = [c.lower() for c in prefs.cuisines]
            out = out[
                out["cuisine_type"].astype(str).str.lower().apply(
                    lambda x: any(w in x for w in wanted)
                )
            ]
        if prefs.allergens_to_avoid and "allergens" in out.columns:
            blocked = [a.lower() for a in prefs.allergens_to_avoid]
            out = out[
                ~out["allergens"].astype(str).str.lower().apply(
                    lambda x: any(b in x for b in blocked)
                )
            ]
        return out

    def _apply_trip_filter(self, df: pd.DataFrame, trip_start: str | None, trip_end: str | None) -> pd.DataFrame:
        if not trip_start or not trip_end or "hawker_center_id" not in df.columns:
            return df
        try:
            closed_ids = self.closure.get_closed_hawker_ids(trip_start, trip_end)
        except Exception:
            return df
        if not closed_ids:
            return df
        out = df.copy()
        out["hawker_center_id"] = pd.to_numeric(out["hawker_center_id"], errors="coerce")
        return out[~out["hawker_center_id"].isin(closed_ids)].copy()

    def _aggregate_stalls(self, df: pd.DataFrame, coords: Coord | None, radius_km: float, top_n: int, m: float) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()
        base = self.stalls_df.copy()
        if "stall_id" not in base.columns:
            return pd.DataFrame()
        if "hawker_center_id" in base.columns and "serial_no" in self.hc_df.columns:
            keep = [c for c in ["serial_no", "name", "latitude_hc", "longitude_hc"] if c in self.hc_df.columns]
            base = base.merge(self.hc_df[keep], left_on="hawker_center_id", right_on="serial_no", how="left")
            if "name" in base.columns:
                base = base.rename(columns={"name": "hawker_name"})
        matched_stalls = df[["stall_id"]].drop_duplicates()
        out = base.merge(matched_stalls, on="stall_id", how="inner")
        scores = self._get_bayes_scores(m=m)
        out = out.merge(scores, on="stall_id", how="left")
        out["n_reviews"] = out["n_reviews"].fillna(0).astype(int)
        out["avg_rating"] = out["avg_rating"].fillna(0.0)
        out["bayes_score"] = out["bayes_score"].fillna(0.0)
        if coords is not None and {"latitude_hc", "longitude_hc"}.issubset(out.columns):
            out["distance_km"] = out.apply(
                lambda r: haversine_km(coords[0], coords[1], float(r["latitude_hc"]), float(r["longitude_hc"])),
                axis=1,
            )
            out = out[out["distance_km"] <= float(radius_km)].copy()
            out = out.sort_values(["distance_km", "bayes_score", "avg_rating"], ascending=[True, False, False])
        else:
            out = out.sort_values(["bayes_score", "avg_rating", "n_reviews"], ascending=[False, False, False])
        return out.head(int(top_n)).reset_index(drop=True)

    def get_top_nearby_stalls(
        self,
        prefs: CuisinePreferences,
        coords: Coord | None,
        radius_km: float = 2.0,
        top_n: int = 5,
        m: float = 20.0,
        trip_start: str | None = None,
        trip_end: str | None = None,
    ) -> pd.DataFrame:
        df = self._apply_pref_filters(self.merged_df, prefs)
        df = self._apply_trip_filter(df, trip_start, trip_end)
        return self._aggregate_stalls(df, coords, radius_km, top_n, m)

    def get_menu_for_stall(self, stall_id: int, prefs: CuisinePreferences | None = None) -> pd.DataFrame:
        out = self.menu_df[self.menu_df["stall_id"] == int(stall_id)].copy()
        if prefs and prefs.allergens_to_avoid and "allergens" in out.columns:
            blocked = [a.lower() for a in prefs.allergens_to_avoid]
            out = out[
                ~out["allergens"].astype(str).str.lower().apply(lambda x: any(b in x for b in blocked))
            ]
        if "price" in out.columns:
            out["price"] = pd.to_numeric(out["price"], errors="coerce")
            out = out.sort_values(["price", "item_name"], ascending=[True, True])
        return out.reset_index(drop=True)

    def get_stalls_by_ids(
        self,
        stall_ids: List[int],
        coords: Coord | None,
        radius_km: float = 3.0,
        trip_start: str | None = None,
        trip_end: str | None = None,
    ) -> pd.DataFrame:
        if not stall_ids:
            return pd.DataFrame()
        df = self.merged_df[self.merged_df["stall_id"].isin([int(x) for x in stall_ids])].copy()
        df = self._apply_trip_filter(df, trip_start, trip_end)
        return self._aggregate_stalls(df, coords, radius_km, top_n=max(5, len(stall_ids)), m=20.0)