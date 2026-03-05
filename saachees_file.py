"""
saachees_file.py
Simple Tourist App (onboarding) — dietary removed

Changes:
- Removed dietary prompts entirely (dataset doesn't support reliable dietary filtering).
- DB still supports legacy columns if present, but we no longer read/write 'dietary'.
- Migration-safe and uses explicit column list for inserts.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

DB_FILE = "tourist_profiles.db"


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
    allergens: List[str]
    preferred_cuisines: List[str]
    created_at: str


# -----------------------------
# Database
# -----------------------------
class TouristProfileDA:
    REQUIRED_COLUMNS = {
        "username": "TEXT",
        "password": "TEXT",
        "name": "TEXT",
        "country": "TEXT",
        "spice_level": "INTEGER",
        # legacy column 'dietary' may exist; we ignore it
        "allergens": "TEXT",
        "preferred_cuisines": "TEXT",
        "created_at": "TEXT",
    }

    def __init__(self, db_file: str = DB_FILE):
        self.db_file = db_file
        self._create_table_if_missing()
        self._migrate_table_if_needed()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_file)

    def _table_exists(self) -> bool:
        with self._connect() as con:
            row = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tourist_profiles';"
            ).fetchone()
        return row is not None

    def _get_existing_columns(self) -> List[str]:
        with self._connect() as con:
            rows = con.execute("PRAGMA table_info(tourist_profiles);").fetchall()
        return [r[1] for r in rows]

    def _create_table_if_missing(self) -> None:
        if self._table_exists():
            return

        # Create a schema WITHOUT dietary (but allow older code/table to still work)
        sql = """
        CREATE TABLE IF NOT EXISTS tourist_profiles (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            country TEXT NOT NULL,
            spice_level INTEGER NOT NULL,
            allergens TEXT,
            preferred_cuisines TEXT,
            created_at TEXT NOT NULL
        );
        """
        with self._connect() as con:
            con.execute(sql)
            con.commit()

    def _migrate_table_if_needed(self) -> None:
        if not self._table_exists():
            return

        existing = set(self._get_existing_columns())
        missing = [c for c in self.REQUIRED_COLUMNS.keys() if c not in existing]

        if not missing:
            return

        with self._connect() as con:
            for col in missing:
                col_type = self.REQUIRED_COLUMNS[col]
                if col == "password":
                    con.execute(f"ALTER TABLE tourist_profiles ADD COLUMN {col} {col_type} DEFAULT '';")
                elif col == "created_at":
                    con.execute(f"ALTER TABLE tourist_profiles ADD COLUMN {col} {col_type} DEFAULT '';")
                else:
                    con.execute(f"ALTER TABLE tourist_profiles ADD COLUMN {col} {col_type};")
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
        # Insert using only columns we manage
        sql = """
        INSERT INTO tourist_profiles (
            username, password, name, country, spice_level,
            allergens, preferred_cuisines, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        data = (
            p.username,
            p.password,
            p.name,
            p.country,
            int(p.spice_level),
            self._pack(p.allergens),
            self._pack(p.preferred_cuisines),
            p.created_at,
        )
        with self._connect() as con:
            con.execute(sql, data)
            con.commit()

    def get_profile(self, username: str) -> Optional[TouristProfile]:
        # Select columns safely even if table has extra legacy columns like dietary
        sql = """
        SELECT username, password, name, country, spice_level,
               allergens, preferred_cuisines, created_at
        FROM tourist_profiles
        WHERE username = ?;
        """
        with self._connect() as con:
            row = con.execute(sql, (username,)).fetchone()

        if not row:
            return None

        return TouristProfile(
            username=row[0],
            password=row[1] or "",
            name=row[2] or "",
            country=row[3] or "",
            spice_level=int(row[4] or 0),
            allergens=self._unpack(row[5]),
            preferred_cuisines=self._unpack(row[6]),
            created_at=row[7] or "",
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

    allergens = input_list("Allergens to avoid (comma-separated) [optional]: ")
    cuisines = input_list("Preferred cuisines (comma-separated) [optional]: ")

    profile = TouristProfile(
        username=username,
        password=password,
        name=name,
        country=country,
        spice_level=spice,
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

    if not profile.password:
        print("This account was created before passwords were enabled. Please create a new account.")
        return None

    if profile.password != password:
        print("Wrong password.")
        return None

    print(f"\nWelcome back, {profile.name}!")
    return profile