"""
onboarding.py
Simple Tourist App

Features:
1) Create Account
2) Login
"""

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

    def _connect(self):
        return sqlite3.connect(self.db_file)

    def _create_table(self):
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
    def _unpack(text: str) -> List[str]:
        if not text:
            return []
        return text.split("|")

    def insert_profile(self, p: TouristProfile):
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

    def get_profile(self, username: str):
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
            spice_level=row[4],
            dietary=self._unpack(row[5]),
            allergens=self._unpack(row[6]),
            preferred_cuisines=self._unpack(row[7]),
            created_at=row[8],
        )


# -----------------------------
# Helper Functions
# -----------------------------
def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def input_nonempty(prompt):
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("Please enter a value.")


def input_int(prompt, lo, hi):
    while True:
        try:
            value = int(input(prompt))
            if lo <= value <= hi:
                return value
        except ValueError:
            pass
        print(f"Enter number between {lo} and {hi}.")


def input_dietary():
    print("\nSelect dietary needs:")
    for i, option in enumerate(DIETARY_OPTIONS, start=1):
        print(f"{i}) {option}")

    raw = input("Choose numbers (comma separated) or press Enter: ").strip()
    if not raw:
        return []

    selected = []
    for choice in raw.split(","):
        if choice.strip().isdigit():
            idx = int(choice.strip())
            if 1 <= idx <= len(DIETARY_OPTIONS):
                selected.append(DIETARY_OPTIONS[idx - 1])

    return selected


def input_list(prompt):
    raw = input(prompt).strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",")]


# -----------------------------
# Create Account Flow
# -----------------------------
def create_account(da):
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
    spice = input_int(" What is your spice tolerance from 0-5? ", 0, 5)

    dietary = input_dietary()
    allergens = input_list("Allergens to avoid (comma-separated, e.g. peanut, shellfish) [optional]: ")
    cuisines = input_list("Preferred cuisines (comma-separated, e.g. Chinese, Malay, Indian) [optional]: ")

    profile = TouristProfile(
        username,
        password,
        name,
        country,
        spice,
        dietary,
        allergens,
        cuisines,
        now_iso(),
    )

    try:
        da.insert_profile(profile)
        print("Account created successfully!")
    except sqlite3.IntegrityError:
        print("Username already exists.")


# -----------------------------
# Login Flow
# -----------------------------
def login(da):
    print("\n=== Login ===")

    username = input_nonempty("Username: ")
    password = input_nonempty("Password: ")

    profile = da.get_profile(username)

    if not profile:
        print("User not found.")
        return

    if profile.password != password:
        print("Wrong password.")
        return

    print(f"\nWelcome back, {profile.name}!")
    print(f"Country: {profile.country}")
    print(f"Spice Level: {profile.spice_level}/5")