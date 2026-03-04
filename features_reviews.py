"""
Content:
1. Compute averaged ratings for all stalls and display ranked lists.
2. Let users select stalls they want to visit (build plan_places list).
3. Optimise the visit order using linear-distance and render a Folium map.
4. Allow users to submit new reviews (OOP - Review / ReviewManager classes).
"""

# CONSTANTS / CONFIGURATION
db_path = "tourist_profiles.db"
stalls_data = "stalls.csv"
reviews_data = "reviews.csv"

"""
Bayesian method is chosen to calculate the average rating for each stalls. 
Explanation: It treats every stall as if it starts with a set of baseline reviews equal to the overall average of the dataset, and as the stall gets real reviews, the score moves toward its true average. 

bayes_prior_mean = global average rating across all stalls
bayes_prior_count = mean number of reviews per stall
"""

import math
import os
import sqlite3
from datetime import datetime, timezone
import pandas as pd

class ReviewFeature:
    def __init__(self,
                 project_root: str = None,
                 stalls_path: str = None,
                 reviews_path: str = None,
                 db_path: str = "tourist_profiles.db"):
        self.project_root = project_root or os.path.dirname(os.path.abspath(__file__))
        default_data_dir = os.path.join(self.project_root, "dataset", "Multiple Stalls Menu and Data")

        self.stalls_path = stalls_path or os.path.join(default_data_dir, "stalls.csv")
        self.reviews_path = reviews_path or os.path.join(default_data_dir, "reviews.csv")
        self.db_path = os.path.join(self.project_root, db_path)

        self.stalls_df = pd.read_csv(self.stalls_path)
        self.reviews_df = pd.read_csv(self.reviews_path)

        self._normalize_reviews_df()
        self._build_stall_name_index()

        print(f"Loaded stalls: {len(self.stalls_df):, } reviews: {len(self.reviews_df):, }")

# Data cleaning / normalization (within the class)
    def _normalize_reviews_df(self):
        # Ensure these columns exist
        if "helpful_count" not in self.reviews_df.columns:
            self.reviews_df["helpful_count"] = 0
        if "is_verified_purchase" not in self.reviews_df.columns:
            self.reviews_df["is_verified_purchase"] = False
            if "review_date" not in self.reviews_df.columns:
                self.reviews_df["review_date"] = datetime.now(timezone.utc).isoformat()

        # Convert types
        self.reviews_df["helpful_count"] = pd.to_numeric(self.reviews_df["helpful_count"], errors="coerce").fillna(
            0).astype(int)
        self.reviews_df["rating"] = pd.to_numeric(self.reviews_df["rating"], errors="coerce").fillna(0).astype(
            float)

        # Convert verified to boolean values
        self.reviews_df["is_verified_purchase"] = (
            self.reviews_df["is_verified_purchase"]
                .astype(str).str.lower()
                .isin(["true", "1", "yes", "y"])
        )

        # Parse dates
        self.reviews_df["review_date"] = pd.to_datetime(self.reviews_df["review_date"], errors="coerce", utc=True)
        self.reviews_df["review_date"] = self.reviews_df["review_date"].fillna(pd.Timestamp.now(tz="UTC"))

    # Stall Name Function
    def _build_stall_name_index(self):
        tmp = self.stalls_df.copy()
        tmp["stall_name_key"] = tmp["stall_name"].astype(str).str.strip().str.lower()
        self.stall_name_to_id = dict(zip(tmp["stall_name_key"], tmp["stall_id"]))

# Bayesian scoring (Average Rating)
    def compute_bayes_scores(self,
                             bayes_m: float = 20.0,
                             helpful_alpha: float = 0.08,
                             verified_bonus: float = 0.05,
                             half_life_days: float = 365.0) -> pd.DataFrame: # These definition is tentative, depends on how the data is, and can be changed later.

        df = self.reviews_df.copy()
        global_mean = df["rating"].mean() if len(df) else 0.0 # Overall average rating of the entire system
        now = pd.Timestamp.now(tz="UTC") # Calculate how old each review
        age_days = (now - df["review_date"]).dt.total_seconds() / 86400.0
        age_days = age_days.clip(lower=0)

        # Weights: Helpfulness, Verified Bonus, Recency Half-Life
        helpful_w = 1.0 + helpful_alpha * df["helpful_count"].apply(lambda x: math.log1p(max(0, int(x)))) # logarithm makes the review grows slowly
        verified_w = df["is_verified_purchase"].apply(lambda v: 1.0 + verified_bonus if bool(v) else 1.0)
        recency_w = (0.5 ** (age_days / half_life_days)).astype(float)

        df["w"] = helpful_w * verified_w * recency_w
        df["w_rating"] = df["rating"] * df["w"]

        agg = df.groupby("stall_id", as_index = False).agg(
            n_reviews=("rating", "count"),
            avg_rating=("rating", "mean"),
            w_sum=("w", "sum"),
            w_rating_sum=("w_rating", "sum"),
        )

        agg["weighted_mean"] = agg["w_rating_sum"] / agg["w_sum"].replace(0, 1e-9)

        # Bayesian average:
        # (m*C + n*R) / (m+n)
        agg["bayes_score"] = (bayes_m * global_mean + agg["n_reviews"] * agg["weighted_mean"]) / (
                bayes_m + agg["n_reviews"])

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
        return df.sort_values(["bayes_score", "avg_rating", "n_reviews"], ascending = [False, False, False])

    def list_reviews_for_stall(self, stall_id: int) -> pd.DataFrame:
        df = self.reviews_df.copy()
        return df[df["stall_id"] == int(stall_id)].sort_values("review_date", ascending=False)

    # Add New Reviews Into Database
    def add_review(
            self,
            stall_name: str,
            rating: float,
            review_text: str,
            user_name: str = None,
    ) -> int:
        if not self.db_path:
            raise ValueError("add_review requires db_path to be set in ReviewFeature(...)")

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
        helpful_count = 0
        is_verified_purchase = False

        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("""
                INSERT INTO reviews (stall_id, user_name, rating, review_text, review_date, helpful_count, is_verified_purchase)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (
                stall_id,
                user_name,
                float(rating),
                str(review_text),
                now_iso,
                int(helpful_count),
                1 if is_verified_purchase else 0,
            ))
            review_id = int(cur.lastrowid)

        # Update in-memory df
        new_row = pd.DataFrame([{
            "review_id": review_id,
            "stall_id": stall_id,
            "user_name": user_name,
            "rating": float(rating),
            "review_text": review_text,
            "review_date": now_iso,
            "helpful_count": helpful_count,
            "is_verified_purchase": is_verified_purchase,
        }])
        self.reviews_df = pd.concat([self.reviews_df, new_row], ignore_index=True)
        self._normalize_reviews_df()

        return review_id

    def mark_review_helpful(self, review_id: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE reviews
                SET helpful_count = helpful_count+1
                WHERE review_id = ?
            """, (review_id,))
            conn.commit()

        if "review_id" in self.reviews_df.columns:
            idx = self.reviews_df["review_id"] == review_id
            self.reviews_df.loc[idx,"helpful_count"] +=1

        print(f"Review {review_id} marked as helpful")