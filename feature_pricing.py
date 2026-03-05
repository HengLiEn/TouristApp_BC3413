"""
Feature: Price Filtering for TouristApp_BC3413
Author: Felicia
Project: Singapore Tourist App BC3413

Integration changes:
- Add helpers to load the default dataset files from /dataset/... so main.py can call this feature
  without asking the user to type filenames and merge keys.
- Keep the original interactive merge workflow available for standalone usage.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Optional

import pandas as pd


class DataManager:
    def __init__(self):
        self.dataframes = []
        self.file_names = []
        self.merge_keys = []

    def load_csv_files(self) -> Optional[pd.DataFrame]:
        file_order = ["1st", "2nd", "3rd"]

        for order in file_order:
            filename = input(f"Enter {order} CSV file you want to merge (or X to stop): ").strip()

            if filename.upper() == "X":
                break

            try:
                df = pd.read_csv(filename)
                self.dataframes.append(df)
                self.file_names.append(filename)
                print(f"{filename} loaded successfully.\n")
            except Exception as e:
                print(f"Error loading file: {e}\n")

        if len(self.dataframes) < 2:
            print("At least 2 CSV files are required to merge.")
            return None

        return self.merge_dataframes()

    def ask_merge_columns(self) -> None:
        print("\n--- Column Selection for Merging ---\n")

        for i in range(len(self.dataframes) - 1):
            print(f"Merging File {i + 1} ({self.file_names[i]}) WITH File {i + 2} ({self.file_names[i + 1]})")

            print("Columns in File 1:")
            print(self.dataframes[i].columns.tolist())
            col1 = input("Enter column name from File 1 to merge on: ").strip()

            print("\nColumns in File 2:")
            print(self.dataframes[i + 1].columns.tolist())
            col2 = input("Enter column name from File 2 to merge on: ").strip()

            self.merge_keys.append((col1, col2))
            print()

    def merge_dataframes(self) -> pd.DataFrame:
        print("Setting merge columns...\n")
        self.ask_merge_columns()

        merged_df = self.dataframes[0]
        for i in range(1, len(self.dataframes)):
            left_key, right_key = self.merge_keys[i - 1]
            merged_df = pd.merge(
                merged_df,
                self.dataframes[i],
                how="inner",
                left_on=left_key,
                right_on=right_key,
            )

        print("Merge completed successfully!\n")
        return merged_df


class DatabaseManager:
    def __init__(self, db_name: str = "tourist_profiles.db"):
        self.conn = sqlite3.connect(db_name)

    def save_to_database(self, df: pd.DataFrame, table_name: str) -> None:
        df.to_sql(table_name, self.conn, if_exists="replace", index=False)
        print(f"Data saved into SQLite database table '{table_name}'.\n")


# -----------------------------
# Integrated helpers for main.py
# -----------------------------
def load_default_merged_dataset(project_root: str = None) -> pd.DataFrame:
    """
    Loads and merges:
    - menu_items.csv (menu items)
    - stalls.csv (stall names, hawker_center_id)
    - hawker_centers.csv (center_name etc.)

    Expected folder structure:
    dataset/Multiple Stalls Menu and Data/menu_items.csv
    dataset/Multiple Stalls Menu and Data/stalls.csv
    dataset/Hawker Centre Data/hawker_centers.csv   (or dataset/Multiple Stalls Menu and Data/hawker_centers.csv)

    If hawker_centers.csv is not found, returns menu_items merged with stalls only.
    """
    root = project_root or os.path.dirname(os.path.abspath(__file__))
    menu_dir = os.path.join(root, "dataset", "Multiple Stalls Menu and Data")
    hc_dir = os.path.join(root, "dataset", "Hawker Centre Data")

    menu_path = os.path.join(menu_dir, "menu_items.csv")
    stalls_path = os.path.join(menu_dir, "stalls.csv")

    # hawker_centers.csv location differs across groups; try both.
    hc_path_1 = os.path.join(hc_dir, "hawker_centers.csv")
    hc_path_2 = os.path.join(menu_dir, "hawker_centers.csv")
    hc_path = hc_path_1 if os.path.exists(hc_path_1) else hc_path_2 if os.path.exists(hc_path_2) else None

    menu_df = pd.read_csv(menu_path)
    stalls_df = pd.read_csv(stalls_path)

    merged = pd.merge(menu_df, stalls_df, how="inner", on="stall_id")

    if hc_path:
        hc_df = pd.read_csv(hc_path)

        # Try to merge hawker centers if keys match common patterns
        if "hawker_center_id" in merged.columns and "center_id" in hc_df.columns:
            merged = pd.merge(merged, hc_df, how="left", left_on="hawker_center_id", right_on="center_id")
        elif "hawker_center_id" in merged.columns and "hawker_center_id" in hc_df.columns:
            merged = pd.merge(merged, hc_df, how="left", on="hawker_center_id")

    return merged


def run_pricing_filter(full_data: pd.DataFrame) -> None:
    """
    Pricing recommender using an already-merged dataset.
    Requires at least: price, category_id, item_name, stall_name (center_name optional).
    category_id assumed:
      1 = Food
      2 = Drinks
    """
    if full_data is None or full_data.empty:
        print("Pricing data not loaded.")
        return

    while True:
        try:
            min_price = float(input("Enter minimum price: ").strip())
            max_price = float(input("Enter maximum price: ").strip())
        except ValueError:
            print("Invalid input. Please enter numeric prices.\n")
            continue

        preference = input("Food (F), Drinks (D), or Both (B)? ").strip().upper()
        if preference not in ("F", "D", "B"):
            print("Invalid preference.\n")
            continue

        filtered = full_data[(full_data["price"] >= min_price) & (full_data["price"] <= max_price)]

        if preference == "F":
            if "category_id" in filtered.columns:
                filtered = filtered[filtered["category_id"] == 1]
        elif preference == "D":
            if "category_id" in filtered.columns:
                filtered = filtered[filtered["category_id"] == 2]
        elif preference == "B":
            if "category_id" in filtered.columns:
                filtered = filtered[filtered["category_id"].isin([1, 2])]

        columns_to_show = ["item_name", "price", "center_name", "stall_name"]
        existing_columns = [col for col in columns_to_show if col in filtered.columns]

        if filtered.empty:
            print("\nNo matching results found.\n")
        else:
            print("\nRecommended Options:\n")
            print(filtered[existing_columns].head(30).to_string(index=False))

        again = input("\nTry another price range? (Y/N): ").strip().upper()
        if again != "Y":
            break


# -----------------------------
# Original standalone workflow
# -----------------------------
def main() -> None:
    data_manager = DataManager()
    db_manager = DatabaseManager()

    full_data = data_manager.load_csv_files()
    if full_data is None:
        return

    db_manager.save_to_database(full_data, "merged_data")
    run_pricing_filter(full_data)


if __name__ == "__main__":
    main()