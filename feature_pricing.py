from __future__ import annotations

import os
from typing import Tuple

import pandas as pd

from feature_cuisines import haversine_km

Coord = Tuple[float, float]


class PriceFeatureHandler:
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

        if "rating" not in self.reviews_df.columns:
            self.reviews_df["rating"] = 0
        self.reviews_df["rating"] = pd.to_numeric(self.reviews_df["rating"], errors="coerce").fillna(0.0)

    def _reviews_summary(self) -> pd.DataFrame:
        if self.reviews_df.empty:
            return pd.DataFrame(columns=["stall_id", "n_reviews", "avg_rating"])
        return self.reviews_df.groupby("stall_id", as_index=False).agg(
            n_reviews=("rating", "count"),
            avg_rating=("rating", "mean"),
        )

    def _get_open_hawker_ids(self, trip_start: str | None, trip_end: str | None) -> set:
        if not trip_start or not trip_end or not self.hawker_id_col:
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
        if "price" not in df.columns:
            return pd.DataFrame()
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
        df = df[(df["price"] >= float(min_price)) & (df["price"] <= float(max_price))].copy()

        pref = (preference or "B").strip().upper()
        if "category_id" in df.columns and pref in {"F", "D", "B"}:
            if pref == "F":
                df = df[df["category_id"] == 1]
            elif pref == "D":
                df = df[df["category_id"] == 2]
            else:
                df = df[df["category_id"].isin([1, 2])]

        if df.empty:
            return pd.DataFrame()

        stall_agg = df.groupby("stall_id", as_index=False).agg(
            matching_avg_price=("price", "mean"),
            matching_items=("stall_id", "count"),
        )
        out = stall_agg.merge(self.stalls_df, on="stall_id", how="left")

        if self.hawker_id_col and "hawker_center_id" in out.columns:
            keep = [c for c in [self.hawker_id_col, self.hawker_name_col, self.lat_col, self.lng_col] if c]
            hc = self.hc_df[keep].copy()
            out = out.merge(hc, left_on="hawker_center_id", right_on=self.hawker_id_col, how="left")
            if self.hawker_name_col and self.hawker_name_col in out.columns:
                out = out.rename(columns={self.hawker_name_col: "hawker_name"})

        out = self._apply_trip_filter(out, trip_start, trip_end)
        out = out.merge(self._reviews_summary(), on="stall_id", how="left")
        out["n_reviews"] = out.get("n_reviews", 0).fillna(0).astype(int)
        out["avg_rating"] = out.get("avg_rating", 0.0).fillna(0.0)

        if coords is not None and self.lat_col and self.lng_col and self.lat_col in out.columns and self.lng_col in out.columns:
            out["distance_km"] = out.apply(
                lambda r: haversine_km(coords[0], coords[1], float(r[self.lat_col]), float(r[self.lng_col]))
                if pd.notna(r[self.lat_col]) and pd.notna(r[self.lng_col]) else float("inf"),
                axis=1,
            )
            out = out[out["distance_km"] <= float(radius_km)].copy()
        else:
            out["distance_km"] = float("inf")

        out = out.sort_values(
            ["matching_avg_price", "distance_km", "avg_rating", "n_reviews"],
            ascending=[True, True, False, False],
        )
        return out.head(int(top_n)).reset_index(drop=True)

    def get_menu_for_stall(self, stall_id: int) -> pd.DataFrame:
        out = self.menu_df[self.menu_df["stall_id"] == int(stall_id)].copy()
        if "price" in out.columns:
            out["price"] = pd.to_numeric(out["price"], errors="coerce")
            out = out.sort_values(["price", "item_name"], ascending=[True, True])
        return out.reset_index(drop=True)