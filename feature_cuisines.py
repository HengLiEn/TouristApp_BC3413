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
    cuisines: List[str] | None = None
    allergens_to_avoid: List[str] | None = None

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
    def __init__(self, project_root: str | None = None):
        self.project_root = project_root or os.path.dirname(os.path.abspath(__file__))
        menu_dir = os.path.join(self.project_root, "dataset", "Multiple Stalls Menu and Data")
        hc_dir = os.path.join(self.project_root, "dataset", "Hawker Centre Data")
        self.menu_path = os.path.join(menu_dir, "menu_items.csv")
        self.stalls_path = os.path.join(menu_dir, "stalls.csv")
        self.reviews_path = os.path.join(menu_dir, "reviews.csv")
        self.hc_path = os.path.join(hc_dir, "DatesofHawkerCentresClosure.csv")

        self.menu_df = pd.read_csv(self.menu_path)
        self.stalls_df = pd.read_csv(self.stalls_path)
        self.reviews_df = pd.read_csv(self.reviews_path)
        self.hc_df = pd.read_csv(self.hc_path)

        self.hawker_id_col = "serial_no" if "serial_no" in self.hc_df.columns else None
        self.hawker_name_col = "name" if "name" in self.hc_df.columns else None
        self.lat_col = "latitude_hc" if "latitude_hc" in self.hc_df.columns else None
        self.lng_col = "longitude_hc" if "longitude_hc" in self.hc_df.columns else ("longtitude_hc" if "longtitude_hc" in self.hc_df.columns else None)

        self._prepare_reviews()
        self._build_merged_df()

    def _prepare_reviews(self) -> None:
        if "rating" not in self.reviews_df.columns:
            self.reviews_df["rating"] = 0
        self.reviews_df["rating"] = pd.to_numeric(self.reviews_df["rating"], errors="coerce").fillna(0.0)

    def _build_merged_df(self) -> None:
        df = self.menu_df.merge(self.stalls_df, on="stall_id", how="left")
        if self.hawker_id_col and "hawker_center_id" in df.columns:
            keep = [c for c in [self.hawker_id_col, self.hawker_name_col, self.lat_col, self.lng_col] if c]
            hc = self.hc_df[keep].copy()
            df = df.merge(hc, left_on="hawker_center_id", right_on=self.hawker_id_col, how="left")
            if self.hawker_name_col and self.hawker_name_col in df.columns:
                df = df.rename(columns={self.hawker_name_col: "hawker_name"})
        self.merged_df = df

    @staticmethod
    def _split_cell(cell: object) -> List[str]:
        if cell is None or (isinstance(cell, float) and pd.isna(cell)):
            return []
        parts = re.split(r"[,;/|]+", str(cell).strip().lower())
        return [p.strip() for p in parts if p.strip()]

    def get_available_cuisines(self) -> List[str]:
        if "cuisine_type" not in self.stalls_df.columns:
            return []
        tokens = set()
        for value in self.stalls_df["cuisine_type"].dropna().astype(str):
            for token in self._split_cell(value):
                tokens.add(token.title())
        return sorted(tokens)

    def save_preferences(self, prefs: CuisinePreferences, username: str) -> None:
        with sqlite3.connect(DB_FILE) as con:
            con.execute(
                "UPDATE tourist_profiles SET preferred_cuisines = ?, allergens = ? WHERE username = ?;",
                (
                    "|".join([x.strip() for x in prefs.cuisines if x.strip()]),
                    "|".join([x.strip() for x in prefs.allergens_to_avoid if x.strip()]),
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
            unpack = lambda s: [x.strip() for x in str(s).split("|") if x.strip()] if s else []
            return CuisinePreferences(cuisines=unpack(row[0]), allergens_to_avoid=unpack(row[1]))
        except Exception:
            return None

    def _get_review_scores(self, m: float = 20.0) -> pd.DataFrame:
        if self.reviews_df.empty:
            return pd.DataFrame(columns=["stall_id", "n_reviews", "avg_rating", "bayes_score"])
        global_mean = self.reviews_df["rating"].mean()
        agg = self.reviews_df.groupby("stall_id", as_index=False).agg(
            n_reviews=("rating", "count"),
            avg_rating=("rating", "mean"),
        )
        agg["bayes_score"] = (m * global_mean + agg["n_reviews"] * agg["avg_rating"]) / (m + agg["n_reviews"])
        return agg

    def _apply_pref_filters(self, df: pd.DataFrame, prefs: CuisinePreferences) -> pd.DataFrame:
        out = df.copy()
        if prefs.cuisines and "cuisine_type" in out.columns:
            wanted = [c.lower() for c in prefs.cuisines]
            out = out[out["cuisine_type"].astype(str).str.lower().apply(lambda x: any(w in x for w in wanted))]
        if prefs.allergens_to_avoid and "allergens" in out.columns:
            blocked = [a.lower() for a in prefs.allergens_to_avoid]
            out = out[~out["allergens"].astype(str).str.lower().apply(lambda x: any(b in x for b in blocked))]
        return out

    def _get_open_hawker_ids(self, trip_start: str | None, trip_end: str | None) -> set:
        if not trip_start or not trip_end or not self.hawker_id_col:
            return set()
        if self.hc_df.empty:
            return set()
        from features_closure import HawkerClosureFeature

        closure = HawkerClosureFeature(project_root=self.project_root)
        try:
            open_df = closure.get_open_hawker_centres(trip_start, trip_end)
        except Exception:
            return set()
        if open_df is None or open_df.empty or self.hawker_id_col not in open_df.columns:
            return set()
        return set(pd.to_numeric(open_df[self.hawker_id_col], errors="coerce").dropna().astype(int).tolist())

    def _apply_trip_filter(self, df: pd.DataFrame, trip_start: str | None, trip_end: str | None) -> pd.DataFrame:
        if not trip_start or not trip_end or "hawker_center_id" not in df.columns:
            return df
        open_ids = self._get_open_hawker_ids(trip_start, trip_end)
        if not open_ids:
            return df
        out = df.copy()
        out["hawker_center_id"] = pd.to_numeric(out["hawker_center_id"], errors="coerce")
        return out[out["hawker_center_id"].isin(open_ids)].copy()

    def _stall_base(self) -> pd.DataFrame:
        base = self.stalls_df.copy()
        if self.hawker_id_col and "hawker_center_id" in base.columns:
            keep = [c for c in [self.hawker_id_col, self.hawker_name_col, self.lat_col, self.lng_col] if c]
            hc = self.hc_df[keep].copy()
            base = base.merge(hc, left_on="hawker_center_id", right_on=self.hawker_id_col, how="left")
            if self.hawker_name_col and self.hawker_name_col in base.columns:
                base = base.rename(columns={self.hawker_name_col: "hawker_name"})
        return base

    def _aggregate_stalls(self, filtered_menu_df: pd.DataFrame, coords: Coord | None, radius_km: float, top_n: int, m: float) -> pd.DataFrame:
        if filtered_menu_df.empty:
            return pd.DataFrame()
        base = self._stall_base()
        out = base.merge(filtered_menu_df[["stall_id"]].drop_duplicates(), on="stall_id", how="inner")
        out = out.merge(self._get_review_scores(m=m), on="stall_id", how="left")
        out["n_reviews"] = out.get("n_reviews", 0).fillna(0).astype(int)
        out["avg_rating"] = out.get("avg_rating", 0.0).fillna(0.0)
        out["bayes_score"] = out.get("bayes_score", 0.0).fillna(0.0)

        if coords is not None and self.lat_col and self.lng_col and self.lat_col in out.columns and self.lng_col in out.columns:
            out["distance_km"] = out.apply(
                lambda r: haversine_km(coords[0], coords[1], float(r[self.lat_col]), float(r[self.lng_col]))
                if pd.notna(r[self.lat_col]) and pd.notna(r[self.lng_col]) else float("inf"),
                axis=1,
            )
            out = out[out["distance_km"] <= float(radius_km)].copy()
            out = out.sort_values(["distance_km", "bayes_score", "avg_rating", "n_reviews"], ascending=[True, False, False, False])
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
            out = out[~out["allergens"].astype(str).str.lower().apply(lambda x: any(b in x for b in blocked))]
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
        ids = [int(x) for x in stall_ids if str(x).strip()]
        if not ids:
            return pd.DataFrame()
        df = self.merged_df[self.merged_df["stall_id"].isin(ids)].copy()
        df = self._apply_trip_filter(df, trip_start, trip_end)
        return self._aggregate_stalls(df, coords, radius_km, max(5, len(ids)), 20.0)