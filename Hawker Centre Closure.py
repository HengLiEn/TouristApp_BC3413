"""
Feature: Hawker Centre Closure Info for TouristApp_BC3413
Author: Skyla
Project: Singapore Tourist App BC3413
Feature Idea: Provide functions to load and filter SG Hawker centre data based on tourist's trip dates.
"""
import os
import pandas as pd
from datetime import datetime
from typing import Optional

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_PATH = os.path.join(
    _BASE_DIR, "dataset", "Hawker Centre Data", "DatesofHawkerCentresClosure.csv"
)

# format date to dd/mm/yyyy
DATE_FORMAT = "%d/%m/%Y"
# treat placeholders for those with no dates set as no closure scheduled
_PLACEHOLDERS = {"tbc", "na", "nil", "n/a", "", "-"}

_CLOSURE_PERIODS = [
    ("q1_cleaningstartdate", "q1_cleaningenddate", "remarks_q1"),
    ("q2_cleaningstartdate", "q2_cleaningenddate", "remarks_q2"),
    ("q3_cleaningstartdate", "q3_cleaningenddate", "remarks_q3"),
    ("q4_cleaningstartdate", "q4_cleaningenddate", "remarks_q4"),
    ("other_works_startdate", "other_works_enddate", "remarks_other_works"),
]

_COLUMNS_TO_KEEP = [
    "serial_no", "name",
    "q1_cleaningstartdate", "q1_cleaningenddate", "remarks_q1",
    "q2_cleaningstartdate", "q2_cleaningenddate", "remarks_q2",
    "q3_cleaningstartdate", "q3_cleaningenddate", "remarks_q3",
    "q4_cleaningstartdate", "q4_cleaningenddate", "remarks_q4",
    "other_works_startdate", "other_works_enddate", "remarks_other_works",
    "address_myenv", "latitude_hc", "longtitude_hc",
    "no_of_food_stalls", "description_myenv", "status",
]

def _parse_date(value) -> Optional[datetime]:
    if pd.isna(value):
        return None
    if str(value).strip().lower() in _PLACEHOLDERS:
        return None
    try:
        return datetime.strptime(str(value).strip(),DATE_FORMAT)
    except ValueError:
        return None

def _parse_date_columns(df: pd.DataFrame) -> pd.DataFrame:
    data_cols = [col for period in _CLOSURE_PERIODS for col in period[:2]]
    df = df.copy()
    for col in date_cols:
        if col in date_cols:
            df[col] =df[col].apply(_parse_date)
    return df

def _get_closure_notes(row: pd.Series,
                        trip_start: datetime,
                        trip_end: datetime) -> list[str]:
    notes = []
    for start_col, en_col, remark_col in _CLOSURE_PERIODS:
        c_start = row.get(start_col)
        c_end = row.get(end_col)
        #if there is no closure scheduled
        if c_start is None or c_end is None:
            continue
        if c_start <= trip_end and c_end >= trip_start:
            remark = str(row.get(remark_col, "")).strip()
            remark_text = (
                f" ({remark})" if remark.lower() not in _PLACEHOLDERS else ""
            )
            notes.append(
                f"Closed {c_start.strftime('%d %m %Y')} - " #is %b a typo"
                f"{c_end.strftime('%d %m %Y')}{remark_text}"
            )
    return notes

def load_hawker_data(filepath: str = _DATA_PATH) -> pd.DataFrame:
    df = pd.read_csv(filepath)
    existing_cols = [c for c in _COLUMNS_TO_KEEP if c in df.columns]
    df = df[existing_cols].copy()
    df = _parse_date_columns(df)
    return df

def get_open_hawker_centres(trip_start_str: str,
                             trip_end_str: str,
                             filepath: str = _DATA_PATH) -> pd.DataFrame:
    trip_start = datetime.strptime(trip_start_str, DATE_FORMAT)
    trip_end = datetime.strptime(trip_end_str, DATE_FORMAT) #what is strptime

    if trip_start > trip_end:
        raise ValueError("trip_start_str must be on or before trip_end_str.")
    df = load_hawker_data(filepath)

    open_rows = []
    for _, row in df.iterrows():
        if not _get_closure_notes(row, trip_start, trip_end):
            open_rows.append(row)

    return pd.DataFrame(open_rows).reset_index(drop=True)

def remove_closed_hawkers(hawker_df: pd.DataFrame,
                           trip_start_str: str,
                           trip_end_str: str) -> pd.DataFrame:
    trip_start = datetime.strptime(trip_start_str, DATE_FORMAT)
    trip_end = datetime.strptime(trip_end_str, DATE_FORMAT)

    if trip_start > trip_end:
        raise ValueError("trip_start_str must be on or before trip_end_str.")

    closure_df = load_hawker_data()
    closure_lookup = {
        row["name"]: row for _, row in closure_df.iterrows()
    }

    open_rows = []
    for _, row in hawker_df.iterrows():
        name = row.get("name", "")
        closure_row = closure_lookup.get(name)
        # if name not found in dataset, assume open and keep it open
        if closure_row is None:
            open_rows.append(row)
            continue

        notes = _get_closure_notes(closure_row, trip_start, trip_end)
        if not notes:
            open_rows.append(row)

    return pd.DataFrame(open_rows).reset_index(drop=True)

#if __name__ == "__main__":
 #   TEST_START = "01/04/2026"
  #  TEST_END = "07/04/2026"

   # print(f"Testing filter for trip: {TEST_START} to {TEST_END}\n")

    #open_df = get_open_hawker_centres(TEST_START, TEST_END)
    #print(f"Open hawker centres : {len(open_df)}")


