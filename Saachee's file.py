import sqlite3
import os
import pandas as pd
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from feature_cuisines import CuisineFeatureHandler, CuisinePreferences
from feature_pricing import DataManager, DatabaseManager
from features_reviews import ReviewFeature
from features_location import LocationPlanner
from features_closure import HawkerClosureFeature
# Nicole: For now I just import everything first. In my mind the overall flow is:
"""
1. Onboard/Login
2. Ask trip dates
3. Filter out closed hawker centres (HawkerClosureFeature)
4. Filter by cuisine preferences (from feature_cuisines)
5. Filter by price (from felicia_project)
6. Attach review stats and sort based on review ranks
7. Let use view stall's revies / add a new review / select stalls to visit
8. Generate best visit sequence (LocationPlanner)
"""

DB_FILE = "tourist_profiles.db"

# ─────────────────────────────────────────
# Dataset paths  (adjust if folder differs)
# ─────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'dataset', 'Multiple Stalls Menu and Data')
DATA_DIR_HAWKER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'dataset', 'Hawker Centre Data')

MENU_CSV   = os.path.join(DATA_DIR, 'menu_items.csv')
STALLS_CSV = os.path.join(DATA_DIR, 'stalls.csv')
HAWKER_CSV = os.path.join(DATA_DIR, 'hawker_centers.csv')
REVIEWS_CSV = os.path.join(DATA_DIR, 'reviews.csv')




# ─────────────────────────────────────────
# Adds a non-interactive CSV loader so we don't
# prompt the user for filenames mid-flow.
# ─────────────────────────────────────────
class AppDataManager(DataManager):
    def load_from_paths(self, paths: list, merge_keys: list):
        """
        Load CSVs from known paths and merge using known keys.
        paths      : list of file path strings
        merge_keys : list of (left_col, right_col) tuples
        """
        self.dataframes = []
        self.file_names = []
        self.merge_keys = merge_keys

        for path in paths:
            try:
                df = pd.read_csv(path)
                self.dataframes.append(df)
                self.file_names.append(path)
                print(f"Loaded: {os.path.basename(path)} ({len(df):,} rows)")
            except Exception as e:
                print(f"Error loading {path}: {e}")

        if len(self.dataframes) < 2:
            print("Not enough files loaded.")
            return None

        return self.merge_dataframes()


# ─────────────────────────────────────────
# Model
# ─────────────────────────────────────────
@dataclass
class TouristProfile:
    user_id: str
    name: str
    country: str
    spice_level: int
    dietary: List[str]
    allergens: List[str]
    preferred_cuisines: List[str]
    created_at: str

    def summary(self) -> str:
        return (
            f"[{self.user_id}] {self.name} (From {self.country}) | "
            f"Spice {self.spice_level}/5 | "
            f"Dietary: {', '.join(self.dietary) if self.dietary else 'None'} | "
            f"Allergens: {', '.join(self.allergens) if self.allergens else 'None'} | "
            f"Cuisines: {', '.join(self.preferred_cuisines) if self.preferred_cuisines else 'Any'}"
        )


# ─────────────────────────────────────────
# DB Access
# ─────────────────────────────────────────
class TouristProfileDA:
    def __init__(self, db_file: str = DB_FILE) -> None:
        self.db_file = db_file
        self._create_table()

    def _connect(self):
        return sqlite3.connect(self.db_file)

    def _create_table(self) -> None:
        sql = """
        CREATE TABLE IF NOT EXISTS tourist_profiles (
            user_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            country TEXT NOT NULL,
            spice_level INTEGER NOT NULL,
            dietary TEXT,
            allergens TEXT,
            preferred_cuisines TEXT,
            created_at TEXT NOT NULL
        );
        """
        with self._connect() as con:
            con.execute(sql)
            con.commit()

    @staticmethod
    def _pack(lst: List[str]) -> str:
        return "|".join([x.strip() for x in lst if x.strip()])

    @staticmethod
    def _unpack(s: Optional[str]) -> List[str]:
        if not s:
            return []
        return [x.strip() for x in s.split("|") if x.strip()]

    def insert_profile(self, p: TouristProfile) -> None:
        sql = "INSERT INTO tourist_profiles VALUES (?, ?, ?, ?, ?, ?, ?, ?);"
        data = (
            p.user_id, p.name, p.country, p.spice_level,
            self._pack(p.dietary), self._pack(p.allergens),
            self._pack(p.preferred_cuisines), p.created_at,
        )
        with self._connect() as con:
            con.execute(sql, data)
            con.commit()

    def get_all_profiles(self) -> List[TouristProfile]:
        sql = "SELECT * FROM tourist_profiles ORDER BY created_at DESC;"
        with self._connect() as con:
            rows = con.execute(sql).fetchall()
        return [
            TouristProfile(
                user_id=r[0], name=r[1], country=r[2],
                spice_level=int(r[3]),
                dietary=self._unpack(r[4]),
                allergens=self._unpack(r[5]),
                preferred_cuisines=self._unpack(r[6]),
                created_at=r[7],
            )
            for r in rows
        ]


# ─────────────────────────────────────────
# Input helpers
# ─────────────────────────────────────────
def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def gen_user_id(name: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    base = "".join([c for c in name.upper() if c.isalnum()])[:8] or "USER"
    return f"{base}-{stamp}"


def input_nonempty(prompt: str) -> str:
    while True:
        s = input(prompt).strip()
        if s:
            return s
        print("Please enter a non-empty value.")


def input_int(prompt: str, lo: int, hi: int) -> int:
    while True:
        try:
            v = int(input(prompt).strip())
            if lo <= v <= hi:
                return v
        except ValueError:
            pass
        print(f"Enter an integer between {lo} and {hi}.")


def input_float(prompt: str) -> float:
    while True:
        try:
            return float(input(prompt).strip())
        except ValueError:
            print("Please enter a valid number.")


def input_list(prompt: str) -> List[str]:
    raw = input(prompt).strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


# ─────────────────────────────────────────
# Onboarding flow
# ─────────────────────────────────────────
def create_profile() -> TouristProfile:
    print("\n=== Tourist Onboarding (New Profile) ===")
    name = input_nonempty("What is your name? ")
    country = input_nonempty("Which country are you from? ")
    spice_level = input_int("Spice tolerance (0-5): ", 0, 5)
    dietary = input_list("Dietary needs (e.g. halal, vegetarian) [optional]: ")
    allergens = input_list("Allergens to avoid (e.g. peanut, shellfish) [optional]: ")
    preferred_cuisines = input_list("Preferred cuisines (e.g. Chinese, Malay, Indian) [optional]: ")

    return TouristProfile(
        user_id=gen_user_id(name),
        name=name,
        country=country,
        spice_level=spice_level,
        dietary=dietary,
        allergens=allergens,
        preferred_cuisines=preferred_cuisines,
        created_at=now_iso(),
    )


# ─────────────────────────────────────────
# Price filter flow  (uses Felicia's data,
# filtering logic lives here so her file
# stays untouched)
# ─────────────────────────────────────────
def filter_by_price(df: pd.DataFrame, min_price: float,
                    max_price: float, preference: str) -> pd.DataFrame:
    preference = preference.upper()
    filtered = df[(df["price"] >= min_price) & (df["price"] <= max_price)]

    if preference == "F":
        filtered = filtered[filtered["category_id"] == 1]
    elif preference == "D":
        filtered = filtered[filtered["category_id"] == 2]
    elif preference == "B":
        filtered = filtered[filtered["category_id"].isin([1, 2])]
    else:
        print("Invalid preference. Showing all price-matched results.")

    return filtered


def display_price_results(filtered: pd.DataFrame):
    columns_to_show = ["item_name", "price", "center_name", "stall_name"]
    existing_columns = [col for col in columns_to_show if col in filtered.columns]

    if filtered.empty:
        print("\nNo matching results found for that price range.\n")
    else:
        print(f"\n{'='*60}")
        print(f"{len(filtered):,} items found in your price range")
        print(f"{'='*60}\n")
        print(filtered[existing_columns].to_string(index=False))


def run_price_filter(full_data: pd.DataFrame):
    print("\n--- Price & Category Filter ---")
    while True:
        min_price = input_float("Minimum price ($): ")
        max_price = input_float("Maximum price ($): ")
        preference = input("Looking for Food (F), Drinks (D), or Both (B)? ").strip()

        filtered = filter_by_price(full_data, min_price, max_price, preference)
        display_price_results(filtered)

        again = input("\nSearch again with different price/category? (Y/N): ").upper()
        if again != "Y":
            break


# ─────────────────────────────────────────
# App startup — load data ONCE
# ─────────────────────────────────────────
print("=== Loading hawker data... ===")

# LiEn's handler (loads menu_items + stalls its own way)
cuisine_handler = CuisineFeatureHandler()

# Felicia's classes used as-is; loading done via our subclass
data_manager = AppDataManager()
full_data = data_manager.load_from_paths(
    paths=[MENU_CSV, STALLS_CSV, HAWKER_CSV],
    merge_keys=[
        ('stall_id',         'stall_id'),
        ('hawker_center_id', 'center_id'),
    ]
)

if full_data is not None:
    db_manager = DatabaseManager()
    db_manager.save_to_database(full_data, "merged_data")
else:
    print("Warning: Could not load hawker data. Price filter will be unavailable.")

da = TouristProfileDA()


# ─────────────────────────────────────────
# Main CLI loop
# ─────────────────────────────────────────
while True:
    print("\n=== Tourist App ===")
    print("1) Create new tourist profile")
    print("2) View all profiles")
    print("0) Exit")
    choice = input("Choose: ").strip()

    if choice == "1":
        # Step 1 — Onboarding (Saachee)
        profile = create_profile()
        da.insert_profile(profile)
        print("\nProfile saved!")
        print(profile.summary())

        # Step 2 — Cuisine filter (LiEn)
        print("\n--- Cuisine Recommendations ---")
        prefs = CuisinePreferences(
            cuisines=profile.preferred_cuisines,
            dietary_restrictions=profile.dietary,
            allergens_to_avoid=profile.allergens,
        )
        cuisine_results = cuisine_handler.filter(prefs)
        cuisine_handler.display(cuisine_results)

        # Step 3 — Price filter (Felicia's data, logic in main.py)
        if full_data is not None:
            run_price_filter(full_data)
        else:
            print("Price filter unavailable (data not loaded).")

    elif choice == "2":
        profiles = da.get_all_profiles()
        if not profiles:
            print("No profiles found.")
        else:
            for p in profiles:
                print("-", p.summary())

    elif choice == "0":
        break

    else:
        print("Invalid option.")
