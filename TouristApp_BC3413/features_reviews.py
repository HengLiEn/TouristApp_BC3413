from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

import pandas as pd


class ReviewFeature:
    def __init__(self, project_root: str | None = None):
        self.project_root = project_root or os.path.dirname(os.path.abspath(__file__))
        menu_dir = os.path.join(self.project_root, "dataset", "Multiple Stalls Menu and Data")
        self.stalls_path = os.path.join(menu_dir, "stalls.csv")
        self.reviews_path = os.path.join(menu_dir, "reviews.csv")

        self.stalls_df = pd.read_csv(self.stalls_path)
        self.reviews_df = pd.read_csv(self.reviews_path)

        self._detect_columns()
        self._normalize_reviews_df()

    def _detect_columns(self) -> None:
        review_cols = set(self.reviews_df.columns)

        self.stall_id_col = "stall_id"
        self.stall_name_col = "stall_name"

        self.review_id_col = self._first_existing(review_cols, ["review_id", "id"])
        self.review_stall_id_col = self._first_existing(review_cols, ["stall_id"])
        self.user_col = self._first_existing(review_cols, ["user_name", "reviewer_name", "reviewer", "username", "user"])
        self.rating_col = self._first_existing(review_cols, ["rating"])
        self.text_col = self._first_existing(review_cols, ["review_text", "review", "text", "comment"])
        self.helpful_col = self._first_existing(review_cols, ["helpful_count", "helpful", "helpful_votes"])
        self.verified_col = self._first_existing(review_cols, ["is_verified_purchase", "verified_purchase", "verified"])
        self.date_col = self._first_existing(review_cols, ["review_date", "date", "created_at", "timestamp"])

        if self.review_stall_id_col is None:
            raise ValueError("reviews.csv must contain a stall_id column")
        if self.rating_col is None:
            self.rating_col = "rating"
            self.reviews_df[self.rating_col] = 0.0
        if self.text_col is None:
            self.text_col = "review_text"
            self.reviews_df[self.text_col] = ""
        if self.user_col is None:
            self.user_col = "user_name"
            self.reviews_df[self.user_col] = "Anonymous"
        if self.helpful_col is None:
            self.helpful_col = "helpful_count"
            self.reviews_df[self.helpful_col] = 0
        if self.verified_col is None:
            self.verified_col = "is_verified_purchase"
            self.reviews_df[self.verified_col] = False
        if self.date_col is None:
            self.date_col = "review_date"
            self.reviews_df[self.date_col] = datetime.now(timezone.utc).date().isoformat()
        if self.review_id_col is None:
            self.review_id_col = "review_id"
            self.reviews_df[self.review_id_col] = range(1, len(self.reviews_df) + 1)

    @staticmethod
    def _first_existing(columns: set[str], candidates: list[str]) -> Optional[str]:
        for c in candidates:
            if c in columns:
                return c
        return None

    def _normalize_reviews_df(self) -> None:
        self.reviews_df[self.rating_col] = pd.to_numeric(self.reviews_df[self.rating_col], errors="coerce").fillna(0.0)
        self.reviews_df[self.helpful_col] = pd.to_numeric(self.reviews_df[self.helpful_col], errors="coerce").fillna(0).astype(int)
        self.reviews_df[self.review_stall_id_col] = pd.to_numeric(self.reviews_df[self.review_stall_id_col], errors="coerce")
        self.reviews_df[self.review_id_col] = pd.to_numeric(self.reviews_df[self.review_id_col], errors="coerce")

        self.reviews_df[self.verified_col] = (
            self.reviews_df[self.verified_col].astype(str).str.strip().str.lower().isin(["true", "1", "yes", "y"])
        )
        dt = pd.to_datetime(self.reviews_df[self.date_col], errors="coerce", utc=True)
        dt = dt.fillna(pd.Timestamp.now(tz="UTC"))
        self.reviews_df[self.date_col] = dt.dt.strftime("%Y-%m-%d")

        self.stalls_df[self.stall_name_col] = self.stalls_df[self.stall_name_col].astype(str)
        self.stalls_df[self.stall_id_col] = pd.to_numeric(self.stalls_df[self.stall_id_col], errors="coerce")

    def save_reviews_csv(self) -> None:
        out = self.reviews_df.copy()
        out.to_csv(self.reviews_path, index=False)

    def search_stalls(self, keyword: str, limit: int = 15) -> pd.DataFrame:
        keyword = (keyword or "").strip().lower()
        if not keyword:
            return pd.DataFrame(columns=self.stalls_df.columns)

        tmp = self.stalls_df.copy()
        tmp["_name_lc"] = tmp[self.stall_name_col].astype(str).str.lower()
        exact = tmp[tmp["_name_lc"] == keyword]
        partial = tmp[tmp["_name_lc"].str.contains(keyword, na=False)]
        out = pd.concat([exact, partial], ignore_index=True).drop_duplicates(subset=[self.stall_id_col])
        return out.head(limit).drop(columns=["_name_lc"], errors="ignore").reset_index(drop=True)

    def get_reviews_for_stall(self, stall_id: int, limit: int = 15) -> pd.DataFrame:
        df = self.reviews_df[self.reviews_df[self.review_stall_id_col] == int(stall_id)].copy()
        if df.empty:
            return df

        df["_date_sort"] = pd.to_datetime(df[self.date_col], errors="coerce")
        df = df.sort_values(["_date_sort", self.helpful_col], ascending=[False, False]).head(limit).reset_index(drop=True)
        df = df.merge(
            self.stalls_df[[self.stall_id_col, self.stall_name_col]],
            left_on=self.review_stall_id_col,
            right_on=self.stall_id_col,
            how="left",
        )
        return df.drop(columns=["_date_sort"], errors="ignore")

    def add_review(self, stall_id: int, rating: float, review_text: str, user_name: str = "Anonymous") -> int:
        rating_f = float(rating)
        if not 0.0 <= rating_f <= 5.0:
            raise ValueError("Rating must be between 0 and 5")

        if not str(review_text).strip():
            raise ValueError("Review text cannot be empty")

        next_id = 1
        if len(self.reviews_df) and self.review_id_col in self.reviews_df.columns:
            nums = pd.to_numeric(self.reviews_df[self.review_id_col], errors="coerce")
            if nums.notna().any():
                next_id = int(nums.max()) + 1

        new_row = {c: None for c in self.reviews_df.columns}
        new_row[self.review_id_col] = next_id
        new_row[self.review_stall_id_col] = int(stall_id)
        new_row[self.user_col] = user_name or "Anonymous"
        new_row[self.rating_col] = rating_f
        new_row[self.text_col] = str(review_text).strip()
        new_row[self.helpful_col] = 0
        new_row[self.verified_col] = False
        new_row[self.date_col] = datetime.now(timezone.utc).date().isoformat()

        self.reviews_df = pd.concat([self.reviews_df, pd.DataFrame([new_row])], ignore_index=True)
        self._normalize_reviews_df()
        self.save_reviews_csv()
        return next_id

    def mark_review_helpful(self, review_id: int) -> None:
        mask = pd.to_numeric(self.reviews_df[self.review_id_col], errors="coerce") == int(review_id)
        if not mask.any():
            raise ValueError("Review not found")
        self.reviews_df.loc[mask, self.helpful_col] = self.reviews_df.loc[mask, self.helpful_col].astype(int) + 1
        self.save_reviews_csv()

    def get_display_rows(self, df: pd.DataFrame) -> list[dict]:
        rows: list[dict] = []
        for _, row in df.iterrows():
            rows.append(
                {
                    "review_id": int(pd.to_numeric(row.get(self.review_id_col), errors="coerce")) if pd.notna(pd.to_numeric(row.get(self.review_id_col), errors="coerce")) else None,
                    "reviewer_name": str(row.get(self.user_col, "Anonymous") or "Anonymous"),
                    "review": str(row.get(self.text_col, "") or ""),
                    "rating": float(pd.to_numeric(row.get(self.rating_col), errors="coerce") or 0.0),
                    "helpful_count": int(pd.to_numeric(row.get(self.helpful_col), errors="coerce") or 0),
                    "verified_purchase": "Yes" if bool(row.get(self.verified_col, False)) else "No",
                    "date": str(row.get(self.date_col, ""))[:10],
                    "stall_name": str(row.get(self.stall_name_col, "") or ""),
                }
            )
        return rows