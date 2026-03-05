"""
features_reviews.py — same behavior, no startup prints
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional, Tuple

import pandas as pd

Coord = Tuple[float, float]


class ReviewFeature:
    def __init__(self, project_root: str = None, db_path: str = "tourist_profiles.db"):
        self.project_root = project_root or os.path.dirname(os.path.abspath(__file__))

        menu_dir = os.path.join(self.project_root, "dataset", "Multiple Stalls Menu and Data")
        self.stalls_path = os.path.join(menu_dir, "stalls.csv")
        self.reviews_path = os.path.join(menu_dir, "reviews.csv")

        self.db_path = os.path.join(self.project_root, db_path)

        self.stalls_df = pd.read_csv(self.stalls_path)
        self.reviews_df = pd.read_csv(self.reviews_path)

        self._normalize_reviews_df()
        self._build_stall_name_index()

        # ✅ removed the noisy print:
        # print(f"Loaded stalls: {len(self.stalls_df):,} | reviews (db): ...")

    def _normalize_reviews_df(self):
        if "helpful_count" not in self.reviews_df.columns:
            self.reviews_df["helpful_count"] = 0
        if "is_verified_purchase" not in self.reviews_df.columns:
            self.reviews_df["is_verified_purchase"] = False
        if "review_date" not in self.reviews_df.columns:
            self.reviews_df["review_date"] = datetime.now(timezone.utc).isoformat()

        self.reviews_df["helpful_count"] = (
            pd.to_numeric(self.reviews_df["helpful_count"], errors="coerce").fillna(0).astype(int)
        )
        self.reviews_df["rating"] = pd.to_numeric(self.reviews_df["rating"], errors="coerce").fillna(0).astype(float)
        self.reviews_df["is_verified_purchase"] = (
            self.reviews_df["is_verified_purchase"].astype(str).str.lower().isin(["true", "1", "yes", "y"])
        )
        self.reviews_df["review_date"] = pd.to_datetime(self.reviews_df["review_date"], errors="coerce", utc=True)
        self.reviews_df["review_date"] = self.reviews_df["review_date"].fillna(pd.Timestamp.now(tz="UTC"))

    def _build_stall_name_index(self):
        tmp = self.stalls_df.copy()
        tmp["stall_name_key"] = tmp["stall_name"].astype(str).str.strip().str.lower()
        self.stall_name_to_id = dict(zip(tmp["stall_name_key"], tmp["stall_id"]))

    # ---- Your existing public methods (unchanged behavior) ----
    def compute_bayes_scores(self, bayes_m: float = 20.0) -> pd.DataFrame:
        df = self.reviews_df.copy()
        global_mean = df["rating"].mean() if len(df) else 0.0

        agg = df.groupby("stall_id", as_index=False).agg(
            n_reviews=("rating", "count"),
            avg_rating=("rating", "mean"),
        )
        agg["bayes_score"] = (bayes_m * global_mean + agg["n_reviews"] * agg["avg_rating"]) / (bayes_m + agg["n_reviews"])
        agg["avg_rating"] = agg["avg_rating"].round(2)
        agg["bayes_score"] = agg["bayes_score"].round(4)
        return agg[["stall_id", "avg_rating", "n_reviews", "bayes_score"]]

    def get_top_stalls(self, n: int = 10) -> pd.DataFrame:
        scores = self.compute_bayes_scores()
        out = self.stalls_df.merge(scores, on="stall_id", how="left")
        out["n_reviews"] = out["n_reviews"].fillna(0).astype(int)
        out["avg_rating"] = out["avg_rating"].fillna(0.0)
        out["bayes_score"] = out["bayes_score"].fillna(0.0)
        out = out.sort_values(["bayes_score", "avg_rating", "n_reviews"], ascending=[False, False, False])
        return out.head(int(n))

    def find_reviews_by_stall_name(self, keyword: str) -> pd.DataFrame:
        keyword = (keyword or "").strip().lower()
        if not keyword:
            return pd.DataFrame()

        matches = self.stalls_df[self.stalls_df["stall_name"].astype(str).str.lower().str.contains(keyword, na=False)]
        if matches.empty:
            return pd.DataFrame()

        ids = set(matches["stall_id"].dropna().astype(int).tolist())
        out = self.reviews_df[self.reviews_df["stall_id"].isin(ids)].copy()
        out = out.merge(matches[["stall_id", "stall_name"]], on="stall_id", how="left")
        out = out.sort_values(["review_date"], ascending=False)
        return out

    def add_review(self, stall_name: str, rating: float, review_text: str, user_name: str = None) -> int:
        try:
            rating_f = float(rating)
        except ValueError:
            raise ValueError("Rating must be a number")
        if not 0.0 <= rating_f <= 5.0:
            raise ValueError("Rating must be between 0 and 5")

        key = stall_name.strip().lower()
        if key not in self.stall_name_to_id:
            raise ValueError(f"Stall name not found in stalls.csv: '{stall_name}'")

        stall_id = int(self.stall_name_to_id[key])
        now_iso = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO reviews (stall_id, user_name, rating, review_text, review_date, helpful_count, is_verified_purchase)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (stall_id, user_name, float(rating_f), str(review_text), now_iso, 0, 0),
            )
            review_id = int(cur.lastrowid)
            conn.commit()

        return review_id

    def mark_review_helpful(self, review_id: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE reviews
                SET helpful_count = helpful_count + 1
                WHERE review_id = ?;
                """,
                (review_id,),
            )
            conn.commit()

        print(f"Review {review_id} marked as helpful")