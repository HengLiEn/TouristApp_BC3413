from __future__ import annotations

import os
from datetime import datetime
from typing import Optional, Set

import pandas as pd


class HawkerClosureFeature:
    DATE_FORMAT = "%d/%m/%Y"
    PLACEHOLDERS = {"", "nil", "na", "n/a", "nan", "none", "tbc", "-"}
    CLOSURE_PERIODS = [
        ("start_date", "end_date", "remarks"),
        ("startdate", "enddate", "remarks"),
        ("closure_start_date", "closure_end_date", "remarks"),
        ("start_date1", "end_date1", "remarks1"),
        ("start_date2", "end_date2", "remarks2"),
        ("start_date3", "end_date3", "remarks3"),
    ]

    def __init__(self, project_root: str = None):
        self.project_root = project_root or os.path.dirname(os.path.abspath(__file__))
        self.filepath = os.path.join(self.project_root, "dataset", "Hawker Centre Data", "DatesofHawkerCentresClosure.csv")
        self._closure_df: Optional[pd.DataFrame] = None

    def _parse_date(self, value) -> Optional[datetime]:
        if pd.isna(value):
            return None
        text = str(value).strip()
        if text.lower() in self.PLACEHOLDERS:
            return None
        for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"]:
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None

    def _candidate_periods(self, df: pd.DataFrame):
        cols = set(df.columns)
        periods = []
        for start_col, end_col, remark_col in self.CLOSURE_PERIODS:
            if start_col in cols and end_col in cols:
                periods.append((start_col, end_col, remark_col if remark_col in cols else None))
        return periods

    def load_hawker_data(self, force_reload: bool = False) -> pd.DataFrame:
        if self._closure_df is not None and not force_reload:
            return self._closure_df
        df = pd.read_csv(self.filepath)
        periods = self._candidate_periods(df)
        for start_col, end_col, _ in periods:
            df[start_col] = df[start_col].apply(self._parse_date)
            df[end_col] = df[end_col].apply(self._parse_date)
        self._closure_df = df
        return df

    def _is_closed_during(self, row: pd.Series, trip_start: datetime, trip_end: datetime) -> bool:
        df = self.load_hawker_data()
        for start_col, end_col, _ in self._candidate_periods(df):
            c_start = row.get(start_col)
            c_end = row.get(end_col)
            if c_start is None or c_end is None:
                continue
            if pd.isna(c_start) or pd.isna(c_end):
                continue
            if c_start <= trip_end and c_end >= trip_start:
                return True
        return False

    def get_open_hawker_centres(self, trip_start_str: str, trip_end_str: str) -> pd.DataFrame:
        trip_start = datetime.strptime(trip_start_str, self.DATE_FORMAT)
        trip_end = datetime.strptime(trip_end_str, self.DATE_FORMAT)
        if trip_start > trip_end:
            raise ValueError("trip_start_str must be on or before trip_end_str.")
        df = self.load_hawker_data()
        open_rows = []
        for _, row in df.iterrows():
            if not self._is_closed_during(row, trip_start, trip_end):
                open_rows.append(row)
        return pd.DataFrame(open_rows).reset_index(drop=True)

    def get_closed_hawker_ids(self, trip_start_str: str, trip_end_str: str) -> Set[int]:
        trip_start = datetime.strptime(trip_start_str, self.DATE_FORMAT)
        trip_end = datetime.strptime(trip_end_str, self.DATE_FORMAT)
        df = self.load_hawker_data()
        ids: Set[int] = set()
        for _, row in df.iterrows():
            if self._is_closed_during(row, trip_start, trip_end):
                serial = row.get("serial_no")
                try:
                    ids.add(int(serial))
                except Exception:
                    pass
        return ids