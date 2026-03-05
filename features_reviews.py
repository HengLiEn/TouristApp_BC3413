"""
Feature: Reviews for TouristApp_BC3413

Content:
1. Compute averaged ratings for all stalls and display ranked lists.
2. View reviews for a stall.
3. Allow users to submit new reviews (stored in SQLite table: reviews).
4. Mark reviews as helpful.

Integration changes:
- Ensure the SQLite table `reviews` exists.
- Seed SQLite reviews table from reviews.csv once (only if table empty).
- Add convenience methods for main.py:
    - get_top_stalls(n)
    - find_reviews_by_stall_name(stall_name)
"""

from __future__ import annotations

import math
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

import pandas as pd


class ReviewFeature:
    def __init__(
        self,
        project_root: str = None,
        stalls_path: str = None,
        reviews_csv_path: str = None,
        db_path: str = "tourist_profiles.db",
    ):
        self.project_root = project_root or os.path.dirname(os.path.abspath(__file__))
        default_data_dir = os.path.join(self.project_root, "dataset", "Multiple Stalls Menu and Data")

        self.stalls_path = stalls_path or os.path.join(default_data_dir, "stalls.csv")
        self.reviews_csv_path = reviews_csv_path or os.path.join(default_data_dir, "reviews.csv")
        self.db_path = db_path  # keep as provided (usually relative to cwd)

        # Load stalls
        self.stalls_df = pd.read_csv(self.stalls_path)

        # DB setup + seed
        self._ensure_reviews_table()
        self._seed_reviews_from_csv_if_needed()

        # Load reviews from DB (source of truth for app actions)
        self.reviews_df = self._read_reviews_from_db()
        self._normalize_reviews_df()
        self._build_stall_name_index()

        print(f"Loaded stalls: {len(self.stalls_df):,} | reviews (db): {len(self.reviews_df):,}")

    # -----------------------------
    # DB setup
    # -----------------------------
    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _ensure_reviews_table(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reviews (
                    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stall_id INTEGER NOT NULL,
                    user_name TEXT,
                    rating REAL NOT NULL,
                    review_text TEXT NOT NULL,
                    review_date TEXT NOT NULL,
                    helpful_count INTEGER NOT NULL DEFAULT 0,
                    is_verified_purchase INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            conn.commit()

    def _db_review_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM reviews;").fetchone()
            return int(row[0]) if row else 0

    def _seed_reviews_from_csv_if_needed(self) -> None:
        """
        If the DB table is empty, seed it from reviews.csv (if present).
        This prevents duplicate inserts on every run.
        """
        if self._db_review_count() > 0:
            return

        if not os.path.exists(self.reviews_csv_path):
            return

        df = pd.read_csv(self.reviews_csv_path)

        # Minimal required columns in CSV
        needed = {"stall_id", "rating", "review_text"}
        if not needed.issubset(set(df.columns)):
            return

        # Optional columns
        if "user_name" not in df.columns:
            df["user_name"] = None
        if "review_date" not in df.columns:
            df["review_date"] = datetime.now(timezone.utc).isoformat()
        if "helpful_count" not in df.columns:
            df["helpful_count"] = 0
        if "is_verified_purchase" not in df.columns:
            df["is_verified_purchase"] = 0

        # Insert
        rows = []
        for _, r in df.iterrows():
            rows.append(
                (
                    int(r["stall_id"]),
                    None if pd.isna(r["user_name"]) else str(r["user_name"]),
                    float(r["rating"]),
                    str(r["review_text"]),
                    str(r["review_date"]),
                    int(r.get("helpful_count", 0) if not pd.isna(r.get("helpful_count", 0)) else 0),
                    1 if str(r.get("is_verified_purchase", "0")).lower() in ("1", "true", "yes", "y") else 0,
                )
            )

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO reviews (stall_id, user_name, rating, review_text, review_date, helpful_count, is_verified_purchase)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                rows,
            )
            conn.commit()

    def _read_reviews_from_db(self) -> pd.DataFrame:
        with self._connect() as conn:
            return pd.read_sql_query("SELECT * FROM reviews;", conn)

    # -----------------------------
    # Data cleaning / normalization
    # -----------------------------
    def _normalize_reviews_df(self) -> None:
        if self.reviews_df is None or self.reviews_df.empty:
            # Ensure columns exist for downstream logic
            self.reviews_df = pd.DataFrame(
                columns=[
                    "review_id",
                    "stall_id",
                    "user_name",
                    "rating",
                    "review_text",
                    "review_date",
                    "helpful_count",
                    "is_verified_purchase",
                ]
            )
            return

        self.reviews_df["helpful_count"] = pd.to_numeric(self.reviews_df["helpful_count"], errors="coerce").fillna(0).astype(int)
        self.reviews_df["rating"] = pd.to_numeric(self.reviews_df["rating"], errors="coerce").fillna(0).astype(float)

        # verified to boolean
        self.reviews_df["is_verified_purchase"] = (
            self.reviews_df["is_verified_purchase"]
            .astype(str).str.lower()
            .isin(["true", "1", "yes", "y"])
        )

        # dates
        self.reviews_df["review_date"] = pd.to_datetime(self.reviews_df["review_date"], errors="coerce", utc=True)
        self.reviews_df["review_date"] = self.reviews_df["review_date"].fillna(pd.Timestamp.now(tz="UTC"))

    def _build_stall_name_index(self) -> None:
        tmp = self.stalls_df.copy()
        tmp["stall_name_key"] = tmp["stall_name"].astype(str).str.strip().str.lower()
        self.stall_name_to_id = dict(zip(tmp["stall_name_key"], tmp["stall_id"]))

    # -----------------------------
    # Bayesian scoring
    # -----------------------------
    def compute_bayes_scores(
        self,
        bayes_m: float = 20.0,
        helpful_alpha: float = 0.08,
        verified_bonus: float = 0.05,
        half_life_days: float = 365.0,
    ) -> pd.DataFrame:
        df = self.reviews_df.copy()
        if df.empty:
            return pd.DataFrame(columns=["stall_id", "avg_rating", "n_reviews", "bayes_score"])

        global_mean = df["rating"].mean()
        now = pd.Timestamp.now(tz="UTC")
        age_days = (now - df["review_date"]).dt.total_seconds() / 86400.0
        age_days = age_days.clip(lower=0)

        helpful_w = 1.0 + helpful_alpha * df["helpful_count"].apply(lambda x: math.log1p(max(0, int(x))))
        verified_w = df["is_verified_purchase"].apply(lambda v: 1.0 + verified_bonus if bool(v) else 1.0)
        recency_w = (0.5 ** (age_days / half_life_days)).astype(float)

        df["w"] = helpful_w * verified_w * recency_w
        df["w_rating"] = df["rating"] * df["w"]

        agg = df.groupby("stall_id", as_index=False).agg(
            n_reviews=("rating", "count"),
            avg_rating=("rating", "mean"),
            w_sum=("w", "sum"),
            w_rating_sum=("w_rating", "sum"),
        )

        agg["weighted_mean"] = agg["w_rating_sum"] / agg["w_sum"].replace(0, 1e-9)
        agg["bayes_score"] = (bayes_m * global_mean + agg["n_reviews"] * agg["weighted_mean"]) / (bayes_m + agg["n_reviews"])

        out = agg[["stall_id", "avg_rating", "n_reviews", "bayes_score"]].copy()
        out["avg_rating"] = out["avg_rating"].round(2)
        out["bayes_score"] = out["bayes_score"].round(4)
        return out

    def attach_scores(self, df: pd.DataFrame) -> pd.DataFrame:
        scores = self.compute_bayes_scores()
        out = df.merge(scores, on="stall_id", how="left")
        out["n_reviews"] = out["n_reviews"].fillna(0).astype(int)
        out["avg_rating"] = out["avg_rating"].fillna(0.0).astype(float)
        out["bayes_score"] = out["bayes_score"].fillna(0.0).astype(float)
        return out

    @staticmethod
    def sort_by_reviews(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        return df.sort_values(["bayes_score", "avg_rating", "n_reviews"], ascending=[False, False, False])

    # -----------------------------
    # Convenience methods for main.py
    # -----------------------------
    def get_top_stalls(self, n: int = 10) -> pd.DataFrame:
        """
        Returns a ranked list of stalls with bayes_score.
        """
        scored = self.attach_scores(self.stalls_df)
        scored = self.sort_by_reviews(scored)
        cols = [c for c in ["stall_id", "stall_name", "cuisine_type", "avg_rating", "n_reviews", "bayes_score"] if c in scored.columns]
        return scored[cols].head(max(1, int(n)))

    def find_reviews_by_stall_name(self, stall_name: str) -> pd.DataFrame:
        key = (stall_name or "").strip().lower()
        if not key:
            return pd.DataFrame()

        # Best-effort: exact match on normalized key
        stall_id = self.stall_name_to_id.get(key)
        if stall_id is None:
            # fallback: contains match
            candidates = [k for k in self.stall_name_to_id.keys() if key in k]
            if not candidates:
                return pd.DataFrame()
            stall_id = self.stall_name_to_id[candidates[0]]

        df = self.reviews_df.copy()
        df = df[df["stall_id"] == int(stall_id)].sort_values("review_date", ascending=False)
        return df

    # -----------------------------
    # Mutations: add review / helpful
    # -----------------------------
    def add_review(
        self,
        stall_name: str,
        rating: float,
        review_text: str,
        user_name: Optional[str] = None,
    ) -> int:
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

        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO reviews (stall_id, user_name, rating, review_text, review_date, helpful_count, is_verified_purchase)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (stall_id, user_name, rating_f, str(review_text), now_iso, 0, 0),
            )
            conn.commit()
            review_id = int(cur.lastrowid)

        # refresh local df
        self.reviews_df = self._read_reviews_from_db()
        self._normalize_reviews_df()

        return review_id

    def mark_review_helpful(self, review_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE reviews
                SET helpful_count = helpful_count + 1
                WHERE review_id = ?;
                """,
                (int(review_id),),
            )
            conn.commit()

        # refresh local df
        self.reviews_df = self._read_reviews_from_db()
        self._normalize_reviews_df()

        print(f"Review {review_id} marked as helpful")