"""
Content:
1. Compute averaged ratings for all stalls and display ranked lists.
2. Let users select stalls they want to visit (build plan_places list).
3. Optimise the visit order using linear-distance and render a Folium map.
4. Allow users to submit new reviews (OOP - Review / ReviewManager classes).

Current Limitation:
- When inputting new review, must match the stall name
- Haven't tested whether the code works with the filtered cuisine df
- How to change the helpful_counter and verify_purchases
"""

# CONSTANTS / CONFIGURATION
db_path = "hawker_trip.db"
# expects an SQLite DB that has already been initialised
stalls_data = "stalls.csv"
reviews_data = "reviews.csv"

"""
Bayesian method is chosen to calculate the average rating for each stalls. 
Explanation: It treats every stall as if it starts with a set of baseline reviews equal to the overall average of the dataset, and as the stall gets real reviews, the score moves toward its true average. 

bayes_prior_mean = global average rating across all stalls
bayes_prior_count = mean number of reviews per stall
"""

import csv, statistics
import math
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List
import pandas as pd

# Will need the CuisinePreferences class from Li En

class ReviewFeature:
    def __init__(self,
                 project_root: str = None,
                 stalls_path: str = None,
                 reviews_path: str = None,
                 db_path: str = "hawker_recommender.db"): # to be changed to combine with the db
        self.project_root = project_root or os.path.dirname(os.path.abspath(__file__))
        default_data_dir = os.path.join(self.project_root, "dataet", "Multiple Stalls Menu and Data")

        self.stalls_path = stalls_path or os.path.join(default_data_dir, "stalls.csv")
        self.reviews_path = reviews_path or os.path.join(default_data_dir, "reviews.csv")
        self.db_path = os.path.join(self.project_root, db_path)

        self.stalls_df = pd.read_csv(self.stalls_path)
        self.reviews_df = pd.read_csv(self.reviews_path)

        self._normalize_reviews_df()
        # self._init_db() - if needed

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

        out = agg.merge(self.stalls_df, on="stalls_id", how="left")

        cols = ["stall_id", "stall_name", "cuisine_type", "specialty_items", "avg_rating", "n_reviews", "bayes_score"]
        out = out[cols].copy()

        out["avg_rating"] = out["avg_rating"].round(2)
        out["bayes_score"] = out["bayes_score"].round(4)

        return out

    # Display Rank
    def rank_filtered_results(self,
                              filtered_df: pd.DataFrame,
                              max_results: int = 20,
                              min_total_reviews: int = 0,
                              min_avg_rating: float = 0.0,) -> pd.DataFrame:
        """
        Input: LiEn's filtered df (already cuisine/dietary filtered)
            Must contain at least: stall_id, stall_name, cuisine_type
        Output: same df + avg_rating/n_reviews/bayes_score, sorted best-first.

        For the minimum total reviews and minimum average rating, its just an optional threshold so we can deliver the "trusted" stalls -> can be deleted
        """
        scores = self.compute_bayes_scores()
        ranked = filtered_df.merge(scores, on="stall_id", how="left") # need to change the filtered_df with the real df from Li En's cuisine preferences

        # If a stall has no reviews, avg_rating/n_reviews/bayes_score will be NaN
        ranked["n_reviews"] = ranked["n_reviews"].fillna(0).astype(int)
        ranked["avg_rating"] = ranked["avg_rating"].fillna(0.0).astype(float)
        ranked["bayes_score"] = ranked["bayes_score"].fillna(0.0).astype(float)

        # Optional thresholds (can be deleted)
        ranked = ranked[ranked["n_reviews"] >= min_total_reviews]
        ranked = ranked[ranked["avg_rating"] >= min_avg_rating]

        ranked = ranked.sort_values(["bayes_score", "n_reviews"], ascending=False)
        return ranked.head(max_results) # will show the top 20, based on the max_results (can be changed)

    # Display Reviews
    def display_ranked(self,
                       ranked_df: pd.DataFrame,
                       max_display: int = 20):
        if ranked_df.empty:
            print("No results to display")
            return

        df = ranked_df.head(max_display).reset_index(drop=True)

        print(f"\n{'=' * 60}\n⭐ Ranked stalls (showing {len(df)})\n{'=' * 60}\n")
        for i, row in df.iterrows():
            print(
                f"{i + 1}. {row.get('stall_name', '(unknown)')} ({row.get('cuisine_type', '')})"
                f"  |  {row['avg_rating']:.2f} / {int(row['n_reviews'])} reviews"
            )
        print()

    # Selection loop -> plan_places (might be redundant with Zi Xing, but for reference purposes)
    def choose_stalls_loop (self, ranked_df: pd.DataFrame) -> List[int]:
        """
        Lets user select stalls by index to append into plan_places.
        Return list of stall_id (plan_places).
        """
        plan_places: List[int] = []
        if ranked_df.empty:
            return plan_places

        df = ranked_df.reset_index(drop=True)
        while True:
            self.display_ranked(df, max_display=min(20, len(df)))

            raw = input(
                "Which stalls do you want to visit? Enter the number (e.g, 1,3,5) (or 'Quit' to stop): ").strip().lower()
            if raw == "Quit":
                break

            try:
                picks = [int(x.strip()) for x in raw.split(",") if x.strip()]
            except ValueError:
                print("Invalid input. Please enter numbers separated by commas (e.g., 1,3,5).\n")
                continue

            for idx in picks:
                if 1 <= idx <= len(df):
                    stall_id = int(df.loc[idx - 1, "stall_id"])
                    if stall_id not in plan_places:
                        plan_places.append(stall_id)

            more = input("Do you want to visit other cuisine / stalls? (Y/N): ").strip().lower()
            if more != "y":
                break

            print("\n(You can input your cuisine preferences and keep adding.)\n")

        return plan_places

    # User Prompt for New Reviews
    def prompt_and_add_review (self, user_name: str) -> int:
        stall_name = input("Stall Name: ").strip() # Limitation: Must match stall name

        while True:
            try:
                rating = float(input("Rating (0 to 5): ").strip())
                if 0.0 <= rating <= 5.0:
                    break
                print("Please enter a rating between 0 and 5.")
            except ValueError:
                print("Please enter a valid number (e.g. 4.5).")

        review_text = input("Review text: ").strip()

        review_id = self.add_review(
            stall_name = stall_name,
            rating = rating,
            review_text = review_text,
            helpful_count = 0,
            user_name = user_name,
            is_verified_purchase=False
        )

        print(f"Review saved (review_id = {review_id}.")
        return review_id

    # Add New Reviews Into Database
    def add_review(
            self,
            stall_name: str,
            rating: float,
            review_text: str,
            helpful_count: int = 0,
            user_name: str = None,
            is_verified_purchase: bool = False, #User_name waiting for Saachee's result
    ) -> int:

        key = stall_name.strip().lower()
        if key not in self.stall_name_to_id:
            raise ValueError(f"Stall name not found in stalls.csv: '{stall_name}'")

        stall_id = int(self.stall_name_to_id[key])
        now_iso = datetime.now(timezone.utc).isoformat()

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
            "helpful_count": int(helpful_count),
            "is_verified_purchase": bool(is_verified_purchase),
        }])
        self.reviews_df = pd.concat([self.reviews_df, new_row], ignore_index=True)
        self._normalize_reviews_df()

        return review_id

