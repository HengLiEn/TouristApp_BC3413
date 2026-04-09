from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

DB_FILE = "tourist_profiles.db"

@dataclass
class TouristProfile:
    username: str
    password: str
    name: str
    allergens: List[str]
    preferred_cuisines: List[str]
    created_at: str
    saved_stalls: List[int] | None = None
    saved_hawker_center_ids: List[int] | None = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    radius_km: float = 2.0
    trip_start: Optional[str] = None
    trip_end: Optional[str] = None
    stall_day_map: dict | None = None
    route_orders: dict | None = None
    country: str = "Singapore"
    spice_level: int = 0

class TouristProfileDA:
    REQUIRED_COLUMNS = {
        "username": "TEXT",
        "password": "TEXT",
        "name": "TEXT",
        "allergens": "TEXT",
        "preferred_cuisines": "TEXT",
        "created_at": "TEXT",
        "saved_stalls": "TEXT",
        "saved_hawker_center_ids": "TEXT",
        "location_lat": "REAL",
        "location_lng": "REAL",
        "radius_km": "REAL",
        "trip_start": "TEXT",
        "trip_end": "TEXT",
        "stall_day_map": "TEXT",
        "route_orders": "TEXT",
    }

    def __init__(self, db_file: str = DB_FILE):
        self.db_file = db_file
        self._create_table_if_missing()
        self._migrate_table_if_needed()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_file)

    def _table_exists(self) -> bool:
        with self._connect() as con:
            row = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tourist_profiles';").fetchone()
        return row is not None

    def _get_existing_columns(self) -> List[str]:
        with self._connect() as con:
            rows = con.execute("PRAGMA table_info(tourist_profiles);").fetchall()
        return [r[1] for r in rows]

    def _create_table_if_missing(self) -> None:
        if self._table_exists():
            return
        sql = """
        CREATE TABLE IF NOT EXISTS tourist_profiles(
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            allergens TEXT,
            preferred_cuisines TEXT,
            created_at TEXT NOT NULL,
            saved_stalls TEXT,
            saved_hawker_center_ids TEXT,
            location_lat REAL,
            location_lng REAL,
            radius_km REAL DEFAULT 2.0,
            trip_start TEXT,
            trip_end TEXT,
            stall_day_map TEXT,
            route_orders TEXT
        );
        """
        with self._connect() as con:
            con.execute(sql)
            con.commit()

    def _migrate_table_if_needed(self) -> None:
        if not self._table_exists():
            return
        existing = set(self._get_existing_columns())
        missing = [c for c in self.REQUIRED_COLUMNS if c not in existing]
        if not missing:
            return

        defaults = {
            "password": " DEFAULT ''",
            "created_at": " DEFAULT ''",
            "saved_stalls": " DEFAULT ''",
            "saved_hawker_center_ids": " DEFAULT ''",
            "radius_km": " DEFAULT 2.0",
            "trip_start": " DEFAULT NULL",
            "trip_end": " DEFAULT NULL",
            "location_lat": " DEFAULT NULL",
            "location_lng": " DEFAULT NULL",
            "stall_day_map": " DEFAULT ''",
            "route_orders": " DEFAULT ''",
        }

        with self._connect() as con:
            for col in missing:
                col_type = self.REQUIRED_COLUMNS[col]
                default = defaults.get(col, "")
                con.execute(f"ALTER TABLE tourist_profiles ADD COLUMN {col} {col_type}{default};")
            con.commit()

    @staticmethod
    def _pack_list(lst: List[str]) -> str:
        return "|".join([str(x).strip() for x in lst if str(x).strip()])

    @staticmethod
    def _unpack_list(text: Optional[str]) -> List[str]:
        if not text:
            return []
        return [x for x in str(text).split("|") if x]

    @staticmethod
    def _pack_ints(values: List[int]) -> str:
        return "|".join(str(int(v)) for v in values)

    @staticmethod
    def _unpack_ints(text: Optional[str]) -> List[int]:
        if not text:
            return []
        out: List[int] = []
        for part in str(text).split("|"):
            part = part.strip()
            if not part:
                continue
            try:
                out.append(int(float(part)))
            except ValueError:
                pass
        return out

    @staticmethod
    def _unique_preserve(seq):
        seen = set()
        out = []
        for item in seq:
            if item in seen:
                continue
            seen.add(item)
            out.append(item)
        return out

    def insert_profile(self, p: TouristProfile) -> None:
        existing_columns = set(self._get_existing_columns())
        payload = {
            "username": p.username,
            "password": p.password,
            "name": p.name,
            "allergens": self._pack_list(p.allergens),
            "preferred_cuisines": self._pack_list(p.preferred_cuisines),
            "created_at": p.created_at,
            "saved_stalls": self._pack_ints(p.saved_stalls or []),
            "saved_hawker_center_ids": self._pack_ints(p.saved_hawker_center_ids or []),
            "location_lat": p.location_lat,
            "location_lng": p.location_lng,
            "radius_km": float(p.radius_km if p.radius_km is not None else 2.0),
            "trip_start": p.trip_start,
            "trip_end": p.trip_end,
            "stall_day_map": json.dumps(p.stall_day_map or {}),
            "route_orders": json.dumps(p.route_orders or {}),
        }

        # Older project schemas may still require these account fields.
        if "country" in existing_columns:
            payload["country"] = p.country or "Singapore"
        if "spice_level" in existing_columns:
            payload["spice_level"] = int(p.spice_level if p.spice_level is not None else 0)

        insert_columns = [col for col in payload if col in existing_columns]
        placeholders = ", ".join(["?"] * len(insert_columns))
        columns_sql = ", ".join(insert_columns)
        sql = f"INSERT INTO tourist_profiles ({columns_sql}) VALUES ({placeholders});"
        data = tuple(payload[col] for col in insert_columns)
        with self._connect() as con:
            con.execute(sql, data)
            con.commit()

    def get_profile(self, username: str) -> Optional[TouristProfile]:
        sql = """
        SELECT username, password, name, allergens, preferred_cuisines, created_at, saved_stalls, saved_hawker_center_ids, location_lat, location_lng, radius_km, trip_start, trip_end, stall_day_map, route_orders
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
            allergens=self._unpack_list(row[3]),
            preferred_cuisines=self._unpack_list(row[4]),
            created_at=row[5] or "",
            saved_stalls=self._unpack_ints(row[6]),
            saved_hawker_center_ids=self._unpack_ints(row[7]),
            location_lat=float(row[8]) if row[8] is not None else None,
            location_lng=float(row[9]) if row[9] is not None else None,
            radius_km=float(row[10]) if row[10] is not None else 2.0,
            trip_start=row[11] if row[11] else None,
            trip_end=row[12] if row[12] else None,
            stall_day_map=json.loads(row[13]) if row[13] else {},
            route_orders=json.loads(row[14]) if row[14] else {},
        )

    def update_preferences(self, username: str, allergens: List[str], preferred_cuisines: List[str]) -> None:
        with self._connect() as con:
            con.execute(
                """
                UPDATE tourist_profiles
                SET allergens = ?, preferred_cuisines = ?
                WHERE username = ?;
                """,
                (self._pack_list(allergens), self._pack_list(preferred_cuisines), username),
            )
            con.commit()

    def _update_int_list_column(self, username: str, column: str, values: List[int]) -> None:
        packed = self._pack_ints(self._unique_preserve([int(v) for v in values]))
        with self._connect() as con:
            con.execute(f"UPDATE tourist_profiles SET {column} = ? WHERE username = ?;", (packed, username))
            con.commit()

    def get_saved_stalls(self, username: str) -> List[int]:
        with self._connect() as con:
            row = con.execute("SELECT saved_stalls FROM tourist_profiles WHERE username = ?;", (username,)).fetchone()
        return self._unpack_ints(row[0] if row else None)

    def add_saved_stall(self, username: str, stall_id: int, hawker_center_id: int | None = None) -> None:
        stalls = self.get_saved_stalls(username)
        stalls.append(int(stall_id))
        self._update_int_list_column(username, "saved_stalls", stalls)
        if hawker_center_id is not None:
            self.add_saved_hawker_centers(username, [int(hawker_center_id)])

    def clear_saved_stalls(self, username: str) -> None:
        with self._connect() as con:
            con.execute(
                "UPDATE tourist_profiles SET saved_stalls = '', saved_hawker_center_ids = '', stall_day_map = '', route_orders = '' WHERE username = ?;",
                (username,),
            )
            con.commit()

    def get_saved_hawker_center_ids(self, username: str) -> List[int]:
        with self._connect() as con:
            row = con.execute("SELECT saved_hawker_center_ids FROM tourist_profiles WHERE username = ?;", (username,)).fetchone()
        return self._unpack_ints(row[0] if row else None)

    def add_saved_hawker_centers(self, username: str, hawker_center_ids: List[int]) -> None:
        existing = self.get_saved_hawker_center_ids(username)
        existing.extend([int(x) for x in hawker_center_ids if x is not None])
        self._update_int_list_column(username, "saved_hawker_center_ids", existing)

    def update_trip_context(
        self,
        username: str,
        coords: Optional[tuple[float, float]],
        radius_km: float,
        trip_start: Optional[str],
        trip_end: Optional[str],
    ) -> None:
        lat = float(coords[0]) if coords is not None else None
        lng = float(coords[1]) if coords is not None else None

        with self._connect() as con:
            con.execute(
                """
                UPDATE tourist_profiles
                SET location_lat = ?,
                    location_lng = ?,
                    radius_km = ?,
                    trip_start = ?,
                    trip_end = ?
                WHERE username = ?;
                """,
                (lat, lng, float(radius_km), trip_start, trip_end, username),
            )
            con.commit()

    def get_stall_day_map(self, username: str) -> dict:
        with self._connect() as con:
            row = con.execute(
                "SELECT stall_day_map FROM tourist_profiles WHERE username = ?;",
                (username,),
            ).fetchone()
        raw = row[0] if row else ""
        return json.loads(raw) if raw else {}

    def update_stall_day_map(self, username: str, mapping: dict) -> None:
        with self._connect() as con:
            con.execute(
                "UPDATE tourist_profiles SET stall_day_map = ? WHERE username = ?;",
                (json.dumps(mapping), username),
            )
            con.commit()

    def get_route_orders(self, username: str) -> dict:
        with self._connect() as con:
            row = con.execute(
                "SELECT route_orders FROM tourist_profiles WHERE username = ?;",
                (username,),
            ).fetchone()
        raw = row[0] if row else ""
        return json.loads(raw) if raw else {}

    def update_route_orders(self, username: str, orders: dict) -> None:
        with self._connect() as con:
            con.execute(
                "UPDATE tourist_profiles SET route_orders = ? WHERE username = ?;",
                (json.dumps(orders), username),
            )
            con.commit()


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
    items = [x.strip() for x in raw.split(",") if x.strip()]
    return TouristProfileDA._unique_preserve(items)

def create_account(da: TouristProfileDA) -> Optional[TouristProfile]:
    print("\n=== Create Account ===")
    username = input_nonempty("Username: ")
    while True:
        password = input_nonempty("Password: ")
        confirm = input_nonempty("Confirm Password: ")
        if password == confirm:
            break
        print("Passwords do not match. Try again.")
    name = input_nonempty("\nWhat is your name? ")
    allergens = input_list("Allergens to avoid (comma-separated) [optional]: ")
    cuisines = input_list("Preferred cuisines (comma-separated) [optional]: ")
    profile = TouristProfile(
        username=username,
        password=password,
        name=name,
        allergens=allergens,
        preferred_cuisines=cuisines,
        created_at=now_iso(),
        saved_stalls=[],
        saved_hawker_center_ids=[],
    )
    try:
        da.insert_profile(profile)
        print("Account created successfully!")
        return profile
    except sqlite3.IntegrityError:
        print("Username already exists.")
        return None

def login(da: TouristProfileDA) -> Optional[TouristProfile]:
    print("=== Login ===")
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
