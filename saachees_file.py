"""
saachees_file.py
Simple Tourist App (onboarding)

Features:
1) Create Account
2) Login

Integration changes:
- create_account(...) returns the created TouristProfile (or None on failure)
- login(...) returns the TouristProfile on success (or None on failure)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

DB_FILE = "tourist_profiles.db"
DIETARY_OPTIONS = ["Vegetarian", "Halal", "Gluten-free", "Vegan", "Dairy-free"]


# -----------------------------
# Model
# -----------------------------
@dataclass
class TouristProfile:
    username: str
    password: str
    name: str
    country: str
    spice_level: int
    dietary: List[str]
    allergens: List[str]
    preferred_cuisines: List[str]
    created_at: str


# -----------------------------
# Database
# -----------------------------
class TouristProfileDA:
    def __init__(self, db_file: str = DB_FILE):
        self.db_file = db_file
        self._create_table()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_file)

    def _create_table(self) -> None:
        sql = """
        CREATE TABLE IF NOT EXISTS tourist_profiles (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
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
        return "|".join(lst)

    @staticmethod
    def _unpack(text: Optional[str]) -> List[str]:
        if not text:
            return []
        return [x for x in text.split("|") if x]

    def insert_profile(self, p: TouristProfile) -> None:
        sql = """
        INSERT INTO tourist_profiles VALUES
        (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        data = (
            p.username,
            p.password,
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

    def get_profile(self, username: str) -> Optional[TouristProfile]:
        sql = "SELECT * FROM tourist_profiles WHERE username = ?;"
        with self._connect() as con:
            row = con.execute(sql, (username,)).fetchone()

        if not row:
            return None

        return TouristProfile(
            username=row[0],
            password=row[1],
            name=row[2],
            country=row[3],
            spice_level=int(row[4]),
            dietary=self._unpack(row[5]),
            allergens=self._unpack(row[6]),
            preferred_cuisines=self._unpack(row[7]),
            created_at=row[8],
        )


# -----------------------------
# Helper Functions
# -----------------------------
def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def input_nonempty(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("Please enter a value.")


def input_int(prompt: str, lo: int, hi: int) -> int:
    while True:
        try:
            value = int(input(prompt))
            if lo <= value <= hi:
                return value
        except ValueError:
            pass
        print(f"Enter number between {lo} and {hi}.")


def input_dietary() -> List[str]:
    print("\nSelect dietary needs:")
    for i, option in enumerate(DIETARY_OPTIONS, start=1):
        print(f"{i}) {option}")

    raw = input("Choose numbers (comma separated) or press Enter: ").strip()
    if not raw:
        return []

    selected: List[str] = []
    for choice in raw.split(","):
        choice = choice.strip()
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(DIETARY_OPTIONS):
                selected.append(DIETARY_OPTIONS[idx - 1])

    # de-duplicate while preserving order
    seen = set()
    deduped: List[str] = []
    for x in selected:
        if x not in seen:
            seen.add(x)
            deduped.append(x)

    return deduped


def input_list(prompt: str) -> List[str]:
    raw = input(prompt).strip()
    if not raw:
        return []
    items = [x.strip() for x in raw.split(",")]
    items = [x for x in items if x]
    seen = set()
    out: List[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# -----------------------------
# Create Account Flow
# -----------------------------
def create_account(da: TouristProfileDA) -> Optional[TouristProfile]:
    print("\n=== Create Account ===")

    username = input_nonempty("Username: ")

    while True:
        password = input_nonempty("Password: ")
        confirm = input_nonempty("Confirm Password: ")

        if password == confirm:
            break
        print("Passwords do not match. Try again.")

    name = input_nonempty("What is your name? ")
    country = input_nonempty("Which country are you from? ")
    spice = input_int("What is your spice tolerance from 0-5? ", 0, 5)

    dietary = input_dietary()
    allergens = input_list("Allergens to avoid (comma-separated) [optional]: ")
    cuisines = input_list("Preferred cuisines (comma-separated) [optional]: ")

    profile = TouristProfile(
        username=username,
        password=password,
        name=name,
        country=country,
        spice_level=spice,
        dietary=dietary,
        allergens=allergens,
        preferred_cuisines=cuisines,
        created_at=now_iso(),
    )

    try:
        da.insert_profile(profile)
        print("Account created successfully!")
        return profile
    except sqlite3.IntegrityError:
        print("Username already exists.")
        return None


# -----------------------------
# Login Flow
# -----------------------------
def login(da: TouristProfileDA) -> Optional[TouristProfile]:
    print("\n=== Login ===")

    username = input_nonempty("Username: ")
    password = input_nonempty("Password: ")

    profile = da.get_profile(username)
    if not profile:
        print("User not found.")
        return None

    if profile.password != password:
        print("Wrong password.")
        return None

    print(f"\nWelcome back, {profile.name}!")
    return profile


if __name__ == "__main__":
    da = TouristProfileDA()
    while True:
        print("\n=== Tourist App ===")
        print("1) Create Account")
        print("2) Login")
        print("0) Exit")

        c = input("Choose: ").strip()
        if c == "1":
            create_account(da)
        elif c == "2":
            login(da)
        elif c == "0":
            break
        else:
            print("Invalid choice.")