from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

import pandas as pd


class ReviewFeature:
    def __init__(self, project_root: str | None = None):
        self.project_root = project_root or os.path.dirname(os.path.abspath(__file__))
        menu_dir = os.path.join(self.project_root, "dataset", "Multiple Stalls Menu and Data")
        self.stalls_path = os.path.join(menu_dir, "stalls.csv")
        self.reviews_path = os.path.join(menu_dir, "reviews.csv")
        self.db_path = os.path.join(self.project_root, "tourist_profiles.db")

        self.stalls_df = pd.read_csv(self.stalls_path)
        self.reviews_df = pd.read_csv(self.reviews_path)

        self._detect_columns()
        self._normalize_reviews_df()
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                review_id            INTEGER PRIMARY KEY AUTOINCREMENT,
                stall_id             INTEGER NOT NULL,
                user_name            TEXT    NOT NULL,
                rating               REAL    NOT NULL,
                review_text          TEXT    NOT NULL,
                review_date          TEXT    NOT NULL,
                helpful_count        INTEGER NOT NULL DEFAULT 0,
                is_verified_purchase INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()

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
        dt = pd.to_datetime(self.reviews_df[self.date_col], format="%Y-%m-%d", errors="coerce", utc=True)
        dt = dt.fillna(pd.Timestamp.now(tz="UTC"))
        self.reviews_df[self.date_col] = dt.dt.strftime("%Y-%m-%d")

        self.stalls_df[self.stall_name_col] = self.stalls_df[self.stall_name_col].astype(str)
        self.stalls_df[self.stall_id_col] = pd.to_numeric(self.stalls_df[self.stall_id_col], errors="coerce")

    def _db_rows_to_df(self, rows: list) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame(columns=[
                self.review_id_col, self.review_stall_id_col, self.user_col,
                self.rating_col, self.text_col, self.date_col,
                self.helpful_col, self.verified_col
            ])
        records = []
        for r in rows:
            records.append({
                self.review_id_col:       r["review_id"],
                self.review_stall_id_col: r["stall_id"],
                self.user_col:            r["user_name"],
                self.rating_col:          r["rating"],
                self.text_col:            r["review_text"],
                self.date_col:            r["review_date"],
                self.helpful_col:         r["helpful_count"],
                self.verified_col:        bool(r["is_verified_purchase"]),
            })
        return pd.DataFrame(records)

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

    def get_reviews_for_stall(self, stall_id: int, limit: int = 200) -> pd.DataFrame:
        csv_df = self.reviews_df[self.reviews_df[self.review_stall_id_col] == int(stall_id)].copy()

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM reviews WHERE stall_id = ?", (int(stall_id),)
        ).fetchall()
        conn.close()
        db_df = self._db_rows_to_df(rows)

        df = pd.concat([csv_df, db_df], ignore_index=True)
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

    def get_reviews_by_user(self, username: str) -> pd.DataFrame:
        csv_df = self.reviews_df[
            self.reviews_df[self.user_col].astype(str).str.lower() == username.lower()
        ].copy()

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM reviews WHERE LOWER(user_name) = LOWER(?)", (username,)
        ).fetchall()
        conn.close()
        db_df = self._db_rows_to_df(rows)

        df = pd.concat([csv_df, db_df], ignore_index=True)
        if df.empty:
            return df

        df["_date_sort"] = pd.to_datetime(df[self.date_col], errors="coerce")
        df = df.sort_values("_date_sort", ascending=False).reset_index(drop=True)
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

        review_date = datetime.now(timezone.utc).date().isoformat()
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            """INSERT INTO reviews (stall_id, user_name, rating, review_text, review_date, helpful_count, is_verified_purchase)
               VALUES (?, ?, ?, ?, ?, 0, 0)""",
            (int(stall_id), user_name or "Anonymous", rating_f, str(review_text).strip(), review_date)
        )
        new_id = cur.lastrowid
        conn.commit()
        conn.close()
        return new_id

    def mark_review_helpful(self, review_id: int) -> None:
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "UPDATE reviews SET helpful_count = helpful_count + 1 WHERE review_id = ?",
            (int(review_id),)
        )
        conn.commit()
        conn.close()
        if cur.rowcount > 0:
            return

        mask = pd.to_numeric(self.reviews_df[self.review_id_col], errors="coerce") == int(review_id)
        if not mask.any():
            raise ValueError("Review not found")
        self.reviews_df.loc[mask, self.helpful_col] = self.reviews_df.loc[mask, self.helpful_col].astype(int) + 1

    def get_avg_rating(self, stall_id: int) -> float | None:
        csv_ratings = pd.to_numeric(
            self.reviews_df.loc[
                self.reviews_df[self.review_stall_id_col] == int(stall_id),
                self.rating_col,
            ],
            errors="coerce",
        ).dropna().tolist()

        conn = sqlite3.connect(self.db_path)
        db_rows = conn.execute(
            "SELECT rating FROM reviews WHERE stall_id = ?", (int(stall_id),)
        ).fetchall()
        conn.close()
        db_ratings = [float(r["rating"]) for r in db_rows]

        all_ratings = csv_ratings + db_ratings
        return sum(all_ratings) / len(all_ratings) if all_ratings else None

    def get_total_review_count(self, stall_id: int) -> int:
        csv_count = int((self.reviews_df[self.review_stall_id_col] == int(stall_id)).sum())

        conn = sqlite3.connect(self.db_path)
        db_count = conn.execute(
            "SELECT COUNT(*) FROM reviews WHERE stall_id = ?", (int(stall_id),)
        ).fetchone()[0]
        conn.close()

        return csv_count + db_count

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


