from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import feature_onboarding
from feature_cuisines import CuisineFeatureHandler, CuisinePreferences
from feature_pricing import PriceFeatureHandler
from features_closure import HawkerClosureFeature
from features_location import LocationPlanner
from features_reviews import ReviewFeature
from features_location import Coord


@dataclass
class SessionContext:
    coords: Optional[Coord] = None
    radius_km: float = 2.0
    trip_start: Optional[str] = None   # dd/mm/yyyy
    trip_end: Optional[str] = None     # dd/mm/yyyy


# -----------------------------
# UI helpers
# -----------------------------
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
    print("1) Browse Menu & Get Recommendations")
    print("2) Itinerary Planner")
    print("3) Reviews")
    print("4) Update Location / Trip Dates")
    print("0) Logout")
    return input("Choose: ").strip()


def reviews_menu() -> str:
    print("\n=== Reviews ===")
    print("1) Top stalls nearby")
    print("2) Read reviews")
    print("3) Write a review")
    print("0) Back")
    return input("Choose: ").strip()


def _fmt_date_range(session: SessionContext) -> str:
    if session.trip_start and session.trip_end:
        return f"{session.trip_start} to {session.trip_end}"
    return "Not set"


def setup_trip_context(planner: LocationPlanner, session: SessionContext) -> None:
    print("\n=== Trip Setup ===")
    print("Please set your location before using the features.")

    while True:
        raw = input("Enter your postal code/address: ").strip()
        coords = planner.get_coords(raw)
        if coords:
            session.coords = coords
            print(f"Location set: ({coords[0]:.6f}, {coords[1]:.6f})")
            break
        print("Could not recognize that location. Please try again.")

    raw_r = input("Nearby radius in km (default 2): ").strip()
    if raw_r:
        try:
            session.radius_km = max(0.1, float(raw_r))
        except ValueError:
            session.radius_km = 2.0
    else:
        session.radius_km = 2.0

    print("\nTrip dates are optional.")
    print("Use dd/mm/yyyy format. Press Enter to skip.")
    start = input("Trip start date: ").strip()
    end = input("Trip end date: ").strip()
    if start and end:
        session.trip_start = start
        session.trip_end = end
        print(f"Trip dates saved: {start} to {end}")
    else:
        session.trip_start = None
        session.trip_end = None
        print("Trip dates skipped. Closed hawker centres will not be excluded.")


def update_trip_context(planner: LocationPlanner, session: SessionContext) -> None:
    print("\n=== Update Location / Trip Dates ===")
    print(f"Current location: {session.coords if session.coords else 'Not set'}")
    print(f"Current nearby radius: {session.radius_km:g} km")
    print(f"Current trip dates: {_fmt_date_range(session)}")
    print("1) Update location")
    print("2) Update trip dates")
    print("3) Update both")
    print("0) Back")
    choice = input("Choose: ").strip()

    if choice == "0":
        return

    if choice in {"1", "3"}:
        while True:
            raw = input("Enter your new postal code/address: ").strip()
            coords = planner.get_coords(raw)
            if coords:
                session.coords = coords
                print(f"Location updated: ({coords[0]:.6f}, {coords[1]:.6f})")
                break
            print("Could not recognize that location. Please try again.")

        raw_r = input(f"Nearby radius in km (current {session.radius_km:g}): ").strip()
        if raw_r:
            try:
                session.radius_km = max(0.1, float(raw_r))
            except ValueError:
                print("Invalid radius. Keeping previous value.")

    if choice in {"2", "3"}:
        print("Press Enter twice if you want to clear the trip dates.")
        start = input("Trip start date (dd/mm/yyyy): ").strip()
        end = input("Trip end date (dd/mm/yyyy): ").strip()
        if start and end:
            session.trip_start = start
            session.trip_end = end
            print(f"Trip dates updated: {start} to {end}")
        elif not start and not end:
            session.trip_start = None
            session.trip_end = None
            print("Trip dates cleared.")
        else:
            print("Please enter both dates together. Keeping previous trip dates.")

def run_cuisine_price_flow(
        cuisine_handler: CuisineFeatureHandler,
        price_handler: PriceFeatureHandler,
        da: feature_onboarding.TouristProfileDA,
        username: str,
        session: SessionContext,
) -> None:

    # Price Preferences
    print("\n=== Browse Menu & Get Recommendations ===")
    try:
        max_price  = float(input("Enter maximum price: ").strip())
    except ValueError:
        print("Please enter valid numeric prices.")
        return

    top = price_handler.get_top_price_recommendations(
        max_price = max_price,
        coords = session.coords,
        radius_km = session.radius_km,
        top_n = 5,
        trip_start = session.trip_start,
        trip_end = session.trip_end,
    )

    if top.empty:
        print("\nNo stalls matched your price preference.")
        return

    # Cuisine Preference
    prefs = cuisine_handler.load_preferences(username) or CuisinePreferences()
    available = cuisine_handler.get_available_cuisines()
    if available:
        preview = ", ".join(available[:20])
        if len(available) > 20:
            preview += " "
        print(f"Available cuisines: {preview}")

    raw_c = input("Enter your cuisine preferences (comma-separated): ").strip()
    if raw_c:
        prefs.cuisines = [x.strip() for x in raw_c.split(",") if x.strip()]
        cuisine_handler.save_preferences(prefs,username)

    filtered_rows = []

    for _, row in top.iterrows():
        stall_id = int(row["stall_id"])
        menu = cuisine_handler.get_menu_for_stall(stall_id, prefs)

        if menu.empty:
            continue

        if "price" in menu.columns:
            menu = menu.copy()
            menu["price"] = pd.to_numeric(menu["price"], errors = "coerce")
            menu = menu[menu["price"] <= float(max_price)].copy()

        if menu.empty:
            continue

        new_row = row.copy()
        new_row["matching_avg_price"] = menu["price"].mean() if "price" in menu.columns else 0.0
        new_row["matcihng_items"] = len(menu)
        filtered_rows.append(new_row)

    if not filtered_rows:
        print("No stalls matched both your price and cuisine preferences.")
        return

    top = pd.DataFrame(filtered_rows)
    sort_cols = []
    ascending = []

    if "matching_avg_price" in top.columns:
        sort_cols.append("matching_avg_price")
        ascending.append(True)
    if "distance_km" in top.columns:
        sort_cols.append("distance_km")
        ascending.append(True)
    if "avg_rating" in top.columns:
        sort_cols.append("avg_rating")
        ascending.append(False)
    if "n_reviews" in top.columns:
        sort_cols.append("n_reviews")
        ascending.append(False)

    if sort_cols:
        top = top.sort_values(sort_cols, ascending=ascending)

    top = top.head(5).reset_index(drop=True)

    _print_stall_cards(top, show_price=True)

    while True:
        choice = input("Enter stall number to view menu (or 0 to go back): ").strip()
        if choice == "0":
            return
        if not choice.isdigit():
            print("Please enter a number.")
            continue

        idx = int(choice) - 1
        if idx < 0 or idx >= len(top):
            print("Invalid stall number.")
            continue

        row = top.iloc[idx]
        stall_id = int(row["stall_id"])
        stall_name = row.get("stall_name", "Unknown stall")
        hawker_name = row.get("hawker_name", "Unknown hawker centre")
        hawker_id = row.get("hawker_center_id")

        menu = cuisine_handler.get_menu_for_stall(stall_id, prefs)
        print("\n" + "=" * 70)
        print(f"Menu for: {stall_name}")
        print("=" * 70)
        if menu.empty:
            print("No menu items found.")
        else:
            cols = [c for c in ["item_name", "price"] if c in menu.columns]
            show_n = 20
            print(menu[cols].head(show_n).to_string(index=False))
            if len(menu) > show_n:
                more = input(f"\nShow all {len(menu)} items? (Y/N): ").strip().lower()
                if more in ("y", "yes"):
                    print("\n" + menu[cols].to_string(index=False))

        add = input(f"\nAdd '{stall_name}' to your itinerary? (Y/N): ").strip().lower()
        if add in ("y", "yes"):
            da.add_saved_stall(username, stall_id, hawker_id)
            print(f"Saved: {stall_name} @ {hawker_name}")
        print()

def run_itinerary_flow(
    cuisine_handler: CuisineFeatureHandler,
    da: feature_onboarding.TouristProfileDA,
    planner: LocationPlanner,
    username: str,
    session: SessionContext,
) -> None:
    print("\n=== Itinerary Planner ===")

    if session.coords is None:
        print("Please set your location first in Feature 5.")
        return

    saved_stalls = da.get_saved_stalls(username)
    if saved_stalls:
        print(f"Using {len(saved_stalls)} saved stall(s) from your profile.")
        candidate = cuisine_handler.get_stalls_by_ids(
            saved_stalls,
            coords=session.coords,
            radius_km=max(session.radius_km, 3.0),
            trip_start=session.trip_start,
            trip_end=session.trip_end,
        )
    else:
        print("No saved stalls found. Creating an itinerary from your profile preferences.")
        prefs = cuisine_handler.load_preferences(username) or CuisinePreferences()
        candidate = cuisine_handler.get_top_nearby_stalls(
            prefs,
            coords=session.coords,
            radius_km=max(session.radius_km, 3.0),
            top_n=12,
            m=20.0,
            trip_start=session.trip_start,
            trip_end=session.trip_end,
        )

    if candidate.empty:
        print("No suitable stalls found for the itinerary.")
        return

    itinerary, total_km, total_mins = planner.build_stall_itinerary(
        start_coords=session.coords,
        stalls_df=candidate,
        max_stops=5,
    )

    if not itinerary:
        print("Could not build an itinerary.")
        return

    print("\n" + "═" * 70)
    print("YOUR WALKABLE ITINERARY")
    print("═" * 70)
    for i, stop in enumerate(itinerary, 1):
        leg = "STARTING POINT" if i == 1 else f"Walk: {stop['leg_dist_km']:.2f} km (~{round(stop['leg_time_mins'])} mins)"
        print(f"\nSTOP {i}: {stop.get('stall_name', 'Unknown stall')}")
        print(f"   Hawker centre: {stop.get('hawker_name', 'Unknown hawker centre')}")
        print(f"   Address: {stop.get('address_myenv', 'N/A')}")
        print(f"   Maps: {stop.get('google_3d_view', 'N/A')}")
        print(f"   {leg}")
        if 'avg_rating' in stop:
            print(f"   Rating: {float(stop.get('avg_rating', 0.0)):.2f} | Reviews: {int(stop.get('n_reviews', 0) or 0)}")

    print("\n" + "-" * 70)
    print(f"Total walking distance: {total_km:.2f} km")
    print(f"Estimated total walking time: {round(total_mins)} mins")
    print("-" * 70)

    hawker_ids = [stop.get("hawker_center_id") for stop in itinerary if stop.get("hawker_center_id") is not None]
    if hawker_ids:
        da.add_saved_hawker_centers(username, hawker_ids)

def choose_index(max_n: int, prompt: str = "Choose number (0 to go back): ") -> Optional[int]:
    while True:
        raw = input(prompt).strip()
        if not raw.isdigit():
            print("Please enter a number.")
            continue
        value = int(raw)
        if value == 0:
            return None
        if 1 <= value <= max_n:
            return value - 1
        print("Invalid choice.")

def save_reviews_csv(reviews: ReviewFeature) -> None:
    reviews.reviews_df.to_csv(reviews.reviews_path, index=False)

def nearby_top_stalls_for_reviews(
    reviews: ReviewFeature,
    pricing: PriceFeatureHandler,
    coords: Coord | None,
    radius_km: float,
    trip_start: str | None,
    trip_end: str | None,
) -> None:
    try:
        min_rating = float(input("Minimum rating (0-5): ").strip() or "0")
    except ValueError:
        min_rating = 0.0

    top = pricing.get_top_price_recommendations(
        min_price=0,
        max_price=9999,
        preference="B",
        coords=coords,
        radius_km=radius_km,
        top_n=50,
        trip_start=trip_start,
        trip_end=trip_end,
    )

    if top.empty:
        print("No stalls found nearby.")
        return

    top = top[top["avg_rating"] >= min_rating].sort_values(
        ["avg_rating", "n_reviews", "distance_km"],
        ascending=[False, False, True],
    ).head(5).reset_index(drop=True)

    if top.empty:
        print("No stalls matched that rating.")
        return

    print("\nTop stalls nearby:")
    for i, row in top.iterrows():
        stall = row.get("stall_name", "Unknown stall")
        hawker = row.get("hawker_name", "Unknown hawker centre")
        dist = row.get("distance_km")
        avg = float(row.get("avg_rating", 0.0) or 0.0)
        n = int(row.get("n_reviews", 0) or 0)
        dist_txt = f"{float(dist):.2f} km" if dist is not None and str(dist) != "nan" else "N/A"
        print(f"[{i + 1}] {stall}  @  {hawker}")
        print(f"     Distance: {dist_txt} | Average Rating: {avg:.2f} | No. of Reviews: {n}\n")


def read_reviews_flow(reviews: ReviewFeature) -> None:
    keyword = input("Enter stall name (exact or close): ").strip()
    if not keyword:
        return

    matches = reviews.stalls_df[
        reviews.stalls_df["stall_name"].astype(str).str.contains(keyword, case=False, na=False)
    ].copy()

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

    reviews.reviews_df.loc[base_mask, "helpful_count"] = (
        pd.to_numeric(reviews.reviews_df.loc[base_mask, "helpful_count"], errors="coerce").fillna(0).astype(int) + 1
    )
    save_reviews_csv(reviews)
    print("Helpful count updated.")


def write_review_flow(reviews: ReviewFeature, username: str) -> None:
    keyword = input("Enter stall name (exact or close): ").strip()
    if not keyword:
        return

    matches = reviews.stalls_df[
        reviews.stalls_df["stall_name"].astype(str).str.contains(keyword, case=False, na=False)
    ].copy()

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


def run_reviews_flow(
    reviews: ReviewFeature,
    pricing: PriceFeatureHandler,
    username: str,
    session: SessionContext,
) -> None:
    while True:
        c = reviews_menu()
        if c == "0":
            return
        if c == "1":
            nearby_top_stalls_for_reviews(
                reviews,
                pricing,
                session.coords,
                session.radius_km,
                session.trip_start,
                session.trip_end,
            )
        elif c == "2":
            read_reviews_flow(reviews)
        elif c == "3":
            write_review_flow(reviews, username)
        else:
            print("Invalid choice.")

def _print_stall_cards(df, show_price: bool = False) -> None:
    print("\nTop Recommended Stalls:")
    print("-" * 70)
    for i, (_, row) in enumerate(df.iterrows(), 1):
        stall = row.get("stall_name", "Unknown stall")
        hawker = row.get("hawker_name", "Unknown hawker centre")
        dist = row.get("distance_km")
        avg = float(row.get("avg_rating", 0.0) or 0.0)
        n = int(row.get("n_reviews", 0) or 0)
        dist_txt = f"{float(dist):.2f} km" if dist is not None and str(dist) != "nan" else "N/A"
        print(f"[{i}] {stall}  @  {hawker}")
        extras = f"     Distance: {dist_txt} | Average Rating: {avg:.2f} | No. of Reviews: {n}"
        if show_price and "matching_avg_price" in row:
            extras += f" | Avg Matching Price: ${float(row['matching_avg_price']):.2f}"
        print(extras + "\n")


def main() -> None:
    print_banner()

    da = feature_onboarding.TouristProfileDA()
    cuisine_handler = CuisineFeatureHandler()
    pricing_handler = PriceFeatureHandler()
    location_planner = LocationPlanner()
    reviews_feature = ReviewFeature()

    current_user: Optional[feature_onboarding.TouristProfile] = None
    session = SessionContext()

    while True:
        if current_user is None:
            c = auth_menu()
            if c == "1":
                created = feature_onboarding.create_account(da)
                if created:
                    auto = input("\nLogin now? (Y/N): ").strip().lower()
                    if auto in ("y", "yes"):
                        current_user = feature_onboarding.login(da)
                        if current_user:
                            setup_trip_context(location_planner, session)
            elif c == "2":
                current_user = feature_onboarding.login(da)
                if current_user:
                    setup_trip_context(location_planner, session)
            elif c == "0":
                print("Bye!")
                return
            else:
                print("Invalid choice.")
            continue

        choice = main_menu()
        if choice == "1":
            run_cuisine_price_flow(cuisine_handler, pricing_handler, da, current_user.username, session)
        elif choice == "2":
            run_itinerary_flow(cuisine_handler, da, location_planner, current_user.username, session)
        elif choice == "3":
            run_reviews_flow(reviews_feature, pricing_handler, current_user.username, session)
        elif choice == "4":
            update_trip_context(location_planner, session)
        elif choice == "0":
            print("Logged out.")
            current_user = None
            session = SessionContext()
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()