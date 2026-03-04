import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from feature_cuisines import CuisineFeatureHandler, CuisinePreferences
import feature_pricing

DB_FILE = "tourist_profiles.db"


# -----------------------------
# Model (OOP)
# -----------------------------
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


# -----------------------------
# DB Access (SQLite)
# -----------------------------
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
        sql = """
        INSERT INTO tourist_profiles VALUES
        (?, ?, ?, ?, ?, ?, ?, ?);
        """
        data = (
            p.user_id,
            p.name,
            p.country,
            p.spice_level,
            self._pack(p.dietary),
            self._pack(p.allergens),
            self._pack(p.preferred_cuisines),
            p.created_at,
        )
        with self._connect() as con:
            con.execute(sql, data)
            con.commit()

    def get_all_profiles(self) -> List[TouristProfile]:
        sql = "SELECT * FROM tourist_profiles ORDER BY created_at DESC;"
        with self._connect() as con:
            rows = con.execute(sql).fetchall()

        profiles = []
        for r in rows:
            profiles.append(
                TouristProfile(
                    user_id=r[0],
                    name=r[1],
                    country=r[2],
                    spice_level=int(r[3]),
                    dietary=self._unpack(r[4]),
                    allergens=self._unpack(r[5]),
                    preferred_cuisines=self._unpack(r[6]),
                    created_at=r[7],
                )
            )
        return profiles


# -----------------------------
# Input helpers
# -----------------------------
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


def input_list(prompt: str) -> List[str]:
    raw = input(prompt).strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


# -----------------------------
# Onboarding flow
# -----------------------------
def create_profile() -> TouristProfile:
    print("\n=== Tourist Onboarding (New Profile) ===")
    name = input_nonempty("What is your name? ")
    country = input_nonempty("Which country are you from? ")
    spice_level = input_int("Spice tolerance (0-5): ", 0, 5)

    dietary = input_list("Dietary needs (comma-separated, e.g. halal, vegetarian) [optional]: ")
    allergens = input_list("Allergens to avoid (comma-separated, e.g. peanut, shellfish) [optional]: ")
    preferred_cuisines = input_list("Preferred cuisines (comma-separated, e.g. Chinese, Malay, Indian) [optional]: ")

    user_id = gen_user_id(name)

    return TouristProfile(
        user_id=user_id,
        name=name,
        country=country,
        spice_level=spice_level,
        dietary=dietary,
        allergens=allergens,
        preferred_cuisines=preferred_cuisines,
        created_at=now_iso(),
    )


# -----------------------------
# CLI
# -----------------------------

da = TouristProfileDA()

while True:
    print("\n=== Tourist App (Main System) ===")
    print("1) Create new tourist profile")
    print("2) View all profiles")
    print("3) Cuisine preference filtering")
    print("4) Price-based recommendation (Felicia)")
    print("0) Exit")

    choice = input("Choose: ").strip()

    # ---------------- OPTION 1 ----------------
    if choice == "1":
        profile = create_profile()
        da.insert_profile(profile)
        print("\nSaved!")
        print(profile.summary())

    # ---------------- OPTION 2 ----------------
    elif choice == "2":
        profiles = da.get_all_profiles()
        if not profiles:
            print("No profiles found.")
        else:
            for p in profiles:
                print("-", p.summary())

    # ---------------- OPTION 3 (YOUR FEATURE) ----------------
    elif choice == "3":
        handler = CuisineFeatureHandler()

        print("\nAvailable cuisines:")
        print(handler.get_available_cuisines())
        cuisines = input_list("Select cuisines (comma-separated, leave blank for all): ")

        print("\nAvailable allergens:")
        print(handler.get_available_allergens())
        allergens = input_list("Allergens to avoid (comma-separated, leave blank for none): ")

        dietary = input_list("Dietary needs e.g. halal, vegetarian (leave blank for none): ")

        prefs = CuisinePreferences(
            cuisines=cuisines,
            dietary_restrictions=dietary,
            allergens_to_avoid=allergens
        )

        df = handler.filter(prefs)
        handler.display(df)

        save = input("Export to CSV? (y/n): ").strip().lower()
        if save == "y":
            handler.export(prefs)

    # ---------------- OPTION 4 (FELICIA FEATURE) ----------------
    elif choice == "4":
        print("\nLaunching price-based recommendation module...\n")
        felicia_file_name.main()   # replace with actual filename

    # ---------------- EXIT ----------------
    elif choice == "0":
        print("Exiting system...")
        break

    else:
        print("Invalid option.")