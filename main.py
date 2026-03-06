from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional, Tuple

import pandas as pd

import saachees_file
from feature_cuisines import CuisineFeatureHandler, CuisinePreferences
from feature_pricing import PriceFeatureHandler
from features_location import LocationPlanner
from features_reviews import ReviewFeature

Coord = Tuple[float, float]
DB_FILE = "tourist_profiles.db"


def print_banner() -> None:
    print("\n" + "=" * 60)
    print("        WELCOME TO HAWKER CENTER GUIDE")
    print("=" * 60)


def auth_menu() -> str:
    print("\n=== Account Page ===")
    print("1) Create Account")
    print("2) Login")
    print("0) Exit")
    return input("Choose: ").strip()


def main_menu() -> str:
    print("\n=== Main Menu ===")
    print("1) Browse Menu & Get Recommendations (Cuisine)")
    print("2) Find Food by Price Range")
    print("3) Itinerary Planner")
    print("4) Reviews")
    print("5) Update Location / Trip Dates")
    print("0) Logout")
    return input("Choose: ").strip()


def reviews_menu() -> str:
    print("\n=== Reviews ===")
    print("1) Top stalls nearby")
    print("2) Read reviews")
    print("3) Write a review")
    print("0) Back")
    return input("Choose: ").strip()


def ensure_profile_columns() -> None:
    with sqlite3.connect(DB_FILE) as con:
        cols = [r[1] for r in con.execute("PRAGMA table_info(tourist_profiles);").fetchall()]
        additions = {
            "saved_stalls": "TEXT DEFAULT ''",
            "saved_hawker_center_ids": "TEXT DEFAULT ''",
            "current_location": "TEXT DEFAULT ''",
            "nearby_radius_km": "REAL DEFAULT 2.0",
            "trip_start": "TEXT DEFAULT ''",
            "trip_end": "TEXT DEFAULT ''",
        }
        for col, ddl in additions.items():
            if col not in cols:
                con.execute(f"ALTER TABLE tourist_profiles ADD COLUMN {col} {ddl};")
        con.commit()


def get_profile_row(username: str) -> dict:
    with sqlite3.connect(DB_FILE) as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM tourist_profiles WHERE username = ?;", (username,)).fetchone()
    return dict(row) if row else {}


def update_profile_fields(username: str, **fields) -> None:
    if not fields:
        return
    keys = list(fields.keys())
    values = [fields[k] for k in keys]
    set_sql = ", ".join([f"{k} = ?" for k in keys])
    with sqlite3.connect(DB_FILE) as con:
        con.execute(f"UPDATE tourist_profiles SET {set_sql} WHERE username = ?;", (*values, username))
        con.commit()


def parse_json_list(raw: object) -> list:
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        value = json.loads(text)
        return value if isinstance(value, list) else []
    except Exception:
        return [x for x in text.split("|") if x]


def save_itinerary_stall(username: str, stall_row: pd.Series) -> None:
    row = get_profile_row(username)
    stalls = parse_json_list(row.get("saved_stalls", ""))
    hc_ids = parse_json_list(row.get("saved_hawker_center_ids", ""))

    stall_id = int(stall_row.get("stall_id"))
    if stall_id not in [int(x) for x in stalls]:
        stalls.append(stall_id)

    hc_id = stall_row.get("hawker_center_id")
    if pd.notna(hc_id):
        hc_id = int(hc_id)
        if hc_id not in [int(x) for x in hc_ids]:
            hc_ids.append(hc_id)

    update_profile_fields(
        username,
        saved_stalls=json.dumps(stalls),
        saved_hawker_center_ids=json.dumps(hc_ids),
    )
    print("Added to itinerary.")


def ask_location_setup(planner: LocationPlanner, current_coords: Optional[Coord] = None, current_radius: float = 2.0) -> tuple[Optional[Coord], float]:
    print("\n=== Trip Setup ===")
    if current_coords is not None:
        print(f"Current location: ({current_coords[0]:.6f}, {current_coords[1]:.6f})")
        print(f"Current nearby radius: {current_radius:g} km")
        keep = input("Keep this location and radius? (Y/N): ").strip().lower()
        if keep in {"y", "yes"}:
            return current_coords, current_radius

    while True:
        raw = input("Enter your location (postal code or address): ").strip()
        coords = planner.get_coords(raw) if raw else None
        if coords:
            break
        print("Could not recognise that location. Try again.")

    radius = current_radius
    raw_r = input("Nearby radius in km (default 2): ").strip()
    if raw_r:
        try:
            radius = max(0.1, float(raw_r))
        except ValueError:
            radius = 2.0
    else:
        radius = 2.0
    return coords, radius


def ask_trip_dates(current_start: str = "", current_end: str = "") -> tuple[str, str]:
    print("\nTrip dates are optional.")
    if current_start and current_end:
        print(f"Current trip dates: {current_start} to {current_end}")
        keep = input("Keep these trip dates? (Y/N): ").strip().lower()
        if keep in {"y", "yes"}:
            return current_start, current_end

    print("Use dd/mm/yyyy format. Press Enter to skip.")
    start = input("Trip start date: ").strip()
    end = input("Trip end date: ").strip()
    if not start or not end:
        return "", ""
    try:
        s = datetime.strptime(start, "%d/%m/%Y")
        e = datetime.strptime(end, "%d/%m/%Y")
        if s > e:
            print("Start date is after end date. Ignoring trip dates.")
            return "", ""
        return start, end
    except ValueError:
        print("Invalid date format. Ignoring trip dates.")
        return "", ""


def format_stall_line(row: pd.Series, index: int, extra: str = "") -> None:
    stall = row.get("stall_name", "Unknown stall")
    hawker = row.get("hawker_name", "Unknown hawker centre")
    dist = row.get("distance_km")
    rating = float(row.get("avg_rating", 0.0) or 0.0)
    n_reviews = int(row.get("n_reviews", 0) or 0)
    dist_txt = f"{float(dist):.2f} km" if pd.notna(dist) and dist != float("inf") else "N/A"
    print(f"[{index}] {stall}  @  {hawker}")
    print(f"     Distance: {dist_txt} | Average Rating: {rating:.2f} | No. of Reviews: {n_reviews}{extra}")


def choose_index(max_n: int, prompt: str = "Choose number (0 to go back): ") -> Optional[int]:
    while True:
        raw = input(prompt).strip()
        if raw == "0":
            return None
        if raw.isdigit() and 1 <= int(raw) <= max_n:
            return int(raw) - 1
        print("Invalid choice.")


def show_menu_table(df: pd.DataFrame) -> None:
    if df.empty:
        print("No menu items found.")
        return
    cols = [c for c in ["item_name", "price"] if c in df.columns]
    if not cols:
        print(df.head(20).to_string(index=False))
        return
    print(df[cols].head(20).to_string(index=False))


def cuisine_flow(handler: CuisineFeatureHandler, username: str, coords: Coord | None, radius_km: float, trip_start: str, trip_end: str) -> None:
    print("\n=== Browse Menu & Get Recommendations (Cuisine) ===")
    saved = handler.load_preferences(username) or CuisinePreferences()
    available = handler.get_available_cuisines()
    if available:
        print("Examples of cuisines:")
        print(", ".join(available[:20]) + (" ..." if len(available) > 20 else ""))
    raw = input("Enter your cuisine preferences (comma-separated): ").strip()
    prefs = CuisinePreferences(
        cuisines=[x.strip() for x in raw.split(",") if x.strip()] if raw else saved.cuisines,
        allergens_to_avoid=saved.allergens_to_avoid,
    )
    handler.save_preferences(prefs, username)

    top = handler.get_top_nearby_stalls(prefs, coords=coords, radius_km=radius_km, top_n=5, trip_start=trip_start, trip_end=trip_end)
    if top.empty:
        print("No matching stalls found.")
        return

    print("\nTop nearby stalls:")
    for i, row in top.iterrows():
        format_stall_line(row, i + 1)

    idx = choose_index(len(top), "Enter stall number to continue (0 to go back): ")
    if idx is None:
        return

    row = top.loc[idx]
    menu = handler.get_menu_for_stall(int(row["stall_id"]), prefs)
    print(f"\nMenu for: {row.get('stall_name', 'Unknown stall')}")
    show_menu_table(menu)

    save = input("\nAdd this stall to your itinerary? (Y/N): ").strip().lower()
    if save in {"y", "yes"}:
        save_itinerary_stall(username, row)


def pricing_flow(handler: PriceFeatureHandler, username: str, coords: Coord | None, radius_km: float, trip_start: str, trip_end: str) -> None:
    print("\n=== Find Food by Price Range ===")
    try:
        min_price = float(input("Minimum price: ").strip())
        max_price = float(input("Maximum price: ").strip())
    except ValueError:
        print("Please enter valid numbers.")
        return
    if min_price > max_price:
        min_price, max_price = max_price, min_price

    pref = input("Food, Drink, or Both? (F/D/B): ").strip().upper() or "B"
    top = handler.get_top_price_recommendations(min_price, max_price, pref, coords, radius_km, 5, trip_start, trip_end)
    if top.empty:
        print("No matching stalls found.")
        return

    print("\nTop nearby stalls by price:")
    for i, row in top.iterrows():
        extra = f" | Matching Avg Price: ${float(row.get('matching_avg_price', 0.0) or 0.0):.2f}"
        format_stall_line(row, i + 1, extra=extra)

    idx = choose_index(len(top), "Enter stall number to continue (0 to go back): ")
    if idx is None:
        return

    row = top.loc[idx]
    menu = handler.get_menu_for_stall(int(row["stall_id"]))
    print(f"\nMenu for: {row.get('stall_name', 'Unknown stall')}")
    show_menu_table(menu)

    save = input("\nAdd this stall to your itinerary? (Y/N): ").strip().lower()
    if save in {"y", "yes"}:
        save_itinerary_stall(username, row)


def itinerary_flow(cuisine_handler: CuisineFeatureHandler, planner: LocationPlanner, username: str, coords: Coord | None, radius_km: float, trip_start: str, trip_end: str) -> None:
    print("\n=== Itinerary Planner ===")
    profile = get_profile_row(username)
    saved_ids = [int(x) for x in parse_json_list(profile.get("saved_stalls", ""))]

    if saved_ids:
        stalls = cuisine_handler.get_stalls_by_ids(saved_ids, coords, radius_km=max(radius_km, 3.0), trip_start=trip_start, trip_end=trip_end)
        if stalls.empty:
            print("Your saved stalls are not available for the current trip settings.")
            return
        print("Using your saved stalls.")
    else:
        prefs = cuisine_handler.load_preferences(username) or CuisinePreferences()
        stalls = cuisine_handler.get_top_nearby_stalls(prefs, coords, radius_km=max(radius_km, 3.0), top_n=5, trip_start=trip_start, trip_end=trip_end)
        if stalls.empty:
            print("Could not build an itinerary from your profile.")
            return
        print("No saved stalls found, so this itinerary is based on your profile.")

    route_df = stalls.copy()
    if "hawker_name" in route_df.columns:
        route_df = route_df.drop_duplicates(subset=["hawker_name"]).head(5)
    route, total_km, total_mins = planner.calculate_best_route(coords, route_df) if coords is not None else ([], 0.0, 0.0)

    if not route:
        print("\nSuggested stops:")
        for i, row in route_df.head(5).iterrows():
            format_stall_line(row, i + 1)
        return

    print("\nSuggested walkable itinerary:")
    for i, stop in enumerate(route, 1):
        name = stop.get("name") or stop.get("hawker_name") or "Unknown hawker centre"
        leg_km = float(stop.get("leg_dist_km", 0.0) or 0.0)
        leg_mins = float(stop.get("leg_time_mins", 0.0) or 0.0)
        print(f"{i}. {name} — walk {leg_km:.2f} km (~{leg_mins:.0f} mins)")
    print(f"\nTotal walking distance: {total_km:.2f} km")
    print(f"Estimated total walking time: {total_mins:.0f} mins")


def save_reviews_csv(reviews: ReviewFeature) -> None:
    reviews.reviews_df.to_csv(reviews.reviews_path, index=False)


def nearby_top_stalls_for_reviews(reviews: ReviewFeature, pricing: PriceFeatureHandler, coords: Coord | None, radius_km: float, trip_start: str, trip_end: str) -> None:
    try:
        min_rating = float(input("Minimum rating (0-5): ").strip() or "0")
    except ValueError:
        min_rating = 0.0
    top = pricing.get_top_price_recommendations(0, 9999, "B", coords, radius_km, 50, trip_start, trip_end)
    if top.empty:
        print("No stalls found nearby.")
        return
    top = top[top["avg_rating"] >= min_rating].sort_values(["avg_rating", "n_reviews", "distance_km"], ascending=[False, False, True]).head(5).reset_index(drop=True)
    if top.empty:
        print("No stalls matched that rating.")
        return
    print("\nTop stalls nearby:")
    for i, row in top.iterrows():
        format_stall_line(row, i + 1)


def read_reviews_flow(reviews: ReviewFeature) -> None:
    keyword = input("Enter stall name (exact or close): ").strip()
    if not keyword:
        return
    matches = reviews.stalls_df[reviews.stalls_df["stall_name"].astype(str).str.contains(keyword, case=False, na=False)].copy()
    if matches.empty:
        print("No stalls matched that name.")
        return
    matches = matches[[c for c in ["stall_id", "stall_name"] if c in matches.columns]].drop_duplicates().head(15).reset_index(drop=True)
    print("\nMatching stalls:")
    for i, row in matches.iterrows():
        print(f"[{i + 1}] {row['stall_name']}")
    idx = choose_index(len(matches), "Choose stall (0 to go back): ")
    if idx is None:
        return
    chosen = matches.loc[idx]
    confirm = input(f"Read reviews for '{chosen['stall_name']}'? (Y/N): ").strip().lower()
    if confirm not in {"y", "yes"}:
        return

    try:
        how_many = min(15, max(1, int(input("How many reviews would you like to see? (max 15): ").strip() or "5")))
    except ValueError:
        how_many = 5

    df = reviews.reviews_df[reviews.reviews_df["stall_id"] == int(chosen["stall_id"])].copy()
    if df.empty:
        print("No reviews found for this stall.")
        return
    if "review_date" in df.columns:
        df["review_date"] = pd.to_datetime(df["review_date"], errors="coerce")
        df = df.sort_values("review_date", ascending=False)
    df = df.head(how_many).reset_index(drop=True)

    print("")
    for i, row in df.iterrows():
        reviewer = row.get("user_name", "Anonymous")
        review_text = row.get("review_text", "")
        rating = float(row.get("rating", 0.0) or 0.0)
        helpful = int(row.get("helpful_count", 0) or 0)
        verified = "Yes" if str(row.get("is_verified_purchase", False)).lower() in {"true", "1", "yes", "y"} or row.get("is_verified_purchase") is True else "No"
        dt = pd.to_datetime(row.get("review_date"), errors="coerce")
        date_only = dt.strftime("%Y-%m-%d") if pd.notna(dt) else "N/A"
        print(f"[{i + 1}] Reviewer: {reviewer}")
        print(f"    Review: {review_text}")
        print(f"    Rating: {rating:.1f} | Helpful Count: {helpful} | Verified Purchase: {verified} | Date: {date_only}")
        print()

    mark = input("Mark a review as helpful? (Y/N): ").strip().lower()
    if mark not in {"y", "yes"}:
        return
    r_idx = choose_index(len(df), "Which review? (0 to cancel): ")
    if r_idx is None:
        return
    chosen_review = df.loc[r_idx]
    confirm = input("Confirm mark this review as helpful? (Y/N): ").strip().lower()
    if confirm not in {"y", "yes"}:
        return

    base_mask = reviews.reviews_df.index == chosen_review.name
    if "review_id" in reviews.reviews_df.columns and pd.notna(chosen_review.get("review_id")):
        base_mask = reviews.reviews_df["review_id"] == chosen_review.get("review_id")
    reviews.reviews_df.loc[base_mask, "helpful_count"] = pd.to_numeric(reviews.reviews_df.loc[base_mask, "helpful_count"], errors="coerce").fillna(0).astype(int) + 1
    save_reviews_csv(reviews)
    print("Helpful count updated.")


def write_review_flow(reviews: ReviewFeature, username: str) -> None:
    keyword = input("Enter stall name (exact or close): ").strip()
    if not keyword:
        return
    matches = reviews.stalls_df[reviews.stalls_df["stall_name"].astype(str).str.contains(keyword, case=False, na=False)].copy()
    if matches.empty:
        print("No stalls matched that name.")
        return
    matches = matches[[c for c in ["stall_id", "stall_name"] if c in matches.columns]].drop_duplicates().head(15).reset_index(drop=True)
    print("\nMatching stalls:")
    for i, row in matches.iterrows():
        print(f"[{i + 1}] {row['stall_name']}")
    idx = choose_index(len(matches), "Choose stall (0 to go back): ")
    if idx is None:
        return
    chosen = matches.loc[idx]
    confirm = input(f"Write a review for '{chosen['stall_name']}'? (Y/N): ").strip().lower()
    if confirm not in {"y", "yes"}:
        return

    try:
        rating = float(input("Rating (0-5): ").strip())
    except ValueError:
        print("Invalid rating.")
        return
    if not 0 <= rating <= 5:
        print("Rating must be between 0 and 5.")
        return
    review_text = input("Write your review: ").strip()
    confirm = input("Submit this review? (Y/N): ").strip().lower()
    if confirm not in {"y", "yes"}:
        return

    row = {
        "stall_id": int(chosen["stall_id"]),
        "user_name": username,
        "rating": float(rating),
        "review_text": review_text,
        "review_date": datetime.now(timezone.utc).date().isoformat(),
        "helpful_count": 0,
        "is_verified_purchase": False,
    }
    if "review_id" in reviews.reviews_df.columns:
        current = pd.to_numeric(reviews.reviews_df["review_id"], errors="coerce").dropna()
        row["review_id"] = int(current.max()) + 1 if not current.empty else 1
    reviews.reviews_df = pd.concat([reviews.reviews_df, pd.DataFrame([row])], ignore_index=True)
    save_reviews_csv(reviews)
    print("Review added.")


def reviews_flow(reviews: ReviewFeature, pricing: PriceFeatureHandler, username: str, coords: Coord | None, radius_km: float, trip_start: str, trip_end: str) -> None:
    while True:
        choice = reviews_menu()
        if choice == "0":
            return
        if choice == "1":
            nearby_top_stalls_for_reviews(reviews, pricing, coords, radius_km, trip_start, trip_end)
        elif choice == "2":
            read_reviews_flow(reviews)
        elif choice == "3":
            write_review_flow(reviews, username)
        else:
            print("Invalid option.")


def main() -> None:
    print_banner()
    da = saachees_file.TouristProfileDA()
    ensure_profile_columns()

    planner = LocationPlanner()
    cuisines = CuisineFeatureHandler()
    pricing = PriceFeatureHandler()
    reviews = ReviewFeature()

    while True:
        choice = auth_menu()
        if choice == "0":
            print("Goodbye.")
            return
        if choice == "1":
            profile = saachees_file.create_account(da)
            if not profile:
                continue
        elif choice == "2":
            profile = saachees_file.login(da)
            if not profile:
                continue
        else:
            print("Invalid option.")
            continue

        user_row = get_profile_row(profile.username)
        saved_loc = parse_json_list(user_row.get("current_location", ""))
        current_coords = tuple(saved_loc) if len(saved_loc) == 2 else None
        current_radius = float(user_row.get("nearby_radius_km") or 2.0)
        trip_start = str(user_row.get("trip_start") or "")
        trip_end = str(user_row.get("trip_end") or "")

        current_coords, current_radius = ask_location_setup(planner, current_coords, current_radius)
        trip_start, trip_end = ask_trip_dates(trip_start, trip_end)
        update_profile_fields(
            profile.username,
            current_location=json.dumps(list(current_coords)) if current_coords else "",
            nearby_radius_km=current_radius,
            trip_start=trip_start,
            trip_end=trip_end,
        )

        while True:
            c = main_menu()
            if c == "0":
                break
            if c == "1":
                cuisine_flow(cuisines, profile.username, current_coords, current_radius, trip_start, trip_end)
            elif c == "2":
                pricing_flow(pricing, profile.username, current_coords, current_radius, trip_start, trip_end)
            elif c == "3":
                itinerary_flow(cuisines, planner, profile.username, current_coords, current_radius, trip_start, trip_end)
            elif c == "4":
                reviews_flow(reviews, pricing, profile.username, current_coords, current_radius, trip_start, trip_end)
            elif c == "5":
                current_coords, current_radius = ask_location_setup(planner, current_coords, current_radius)
                trip_start, trip_end = ask_trip_dates(trip_start, trip_end)
                update_profile_fields(
                    profile.username,
                    current_location=json.dumps(list(current_coords)) if current_coords else "",
                    nearby_radius_km=current_radius,
                    trip_start=trip_start,
                    trip_end=trip_end,
                )
                print("Trip settings updated.")
            else:
                print("Invalid option.")


if __name__ == "__main__":
    main()