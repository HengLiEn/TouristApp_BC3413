from __future__ import annotations

import os
from typing import Optional, Tuple

import pandas as pd

from feature_cuisines import haversine_km
from features_closure import HawkerClosureFeature

Coord = Tuple[float, float]


class PriceFeatureHandler:
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
        self.reviews_df = pd.read_csv(self.reviews_path)
        self.hc_df = pd.read_csv(self.hc_path)
        self.closure = HawkerClosureFeature(project_root=self.project_root)

    def _reviews_summary(self) -> pd.DataFrame:
        df = self.reviews_df.copy()
        df["rating"] = pd.to_numeric(df.get("rating"), errors="coerce").fillna(0.0)
        agg = df.groupby("stall_id", as_index=False).agg(
            n_reviews=("rating", "count"),
            avg_rating=("rating", "mean"),
        )
        return agg

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

    def get_top_price_recommendations(
        self,
        min_price: float,
        max_price: float,
        preference: str,
        coords: Coord | None,
        radius_km: float = 2.0,
        top_n: int = 5,
        trip_start: str | None = None,
        trip_end: str | None = None,
    ) -> pd.DataFrame:
        df = self.menu_df.copy()
        df["price"] = pd.to_numeric(df.get("price"), errors="coerce")
        df = df[(df["price"] >= float(min_price)) & (df["price"] <= float(max_price))].copy()
        if preference in {"F", "D", "B"} and "category_id" in df.columns:
            if preference == "F":
                df = df[df["category_id"] == 1]
            elif preference == "D":
                df = df[df["category_id"] == 2]
            else:
                df = df[df["category_id"].isin([1, 2])]
        if df.empty:
            return pd.DataFrame()
        stall_agg = df.groupby("stall_id", as_index=False).agg(
            matching_avg_price=("price", "mean"),
            matching_items=("item_name", "count"),
        )
        out = stall_agg.merge(self.stalls_df, on="stall_id", how="left")
        if "hawker_center_id" in out.columns and "serial_no" in self.hc_df.columns:
            keep = [c for c in ["serial_no", "name", "latitude_hc", "longitude_hc"] if c in self.hc_df.columns]
            out = out.merge(self.hc_df[keep], left_on="hawker_center_id", right_on="serial_no", how="left")
            if "name" in out.columns:
                out = out.rename(columns={"name": "hawker_name"})
        out = self._apply_trip_filter(out, trip_start, trip_end)
        rev = self._reviews_summary()
        out = out.merge(rev, on="stall_id", how="left")
        out["n_reviews"] = out["n_reviews"].fillna(0).astype(int)
        out["avg_rating"] = out["avg_rating"].fillna(0.0)
        if coords is not None and {"latitude_hc", "longitude_hc"}.issubset(out.columns):
            out["distance_km"] = out.apply(
                lambda r: haversine_km(coords[0], coords[1], float(r["latitude_hc"]), float(r["longitude_hc"])),
                axis=1,
            )
            out = out[out["distance_km"] <= float(radius_km)].copy()
        out = out.sort_values(
            ["matching_avg_price", "distance_km", "avg_rating", "n_reviews"],
            ascending=[True, True, False, False],
        )
        return out.head(int(top_n)).reset_index(drop=True)

    def get_menu_for_stall(self, stall_id: int) -> pd.DataFrame:
        out = self.menu_df[self.menu_df["stall_id"] == int(stall_id)].copy()
        out["price"] = pd.to_numeric(out.get("price"), errors="coerce")
        return out.sort_values(["price", "item_name"], ascending=[True, True]).reset_index(drop=True)