"""
main.py
Adds a "Set your location" step immediately after login.
"""

from __future__ import annotations

from typing import Optional, Tuple

import saachees_file
from feature_cuisines import CuisineFeatureHandler, CuisinePreferences
from feature_pricing import load_default_merged_dataset, run_pricing_filter
from features_closure import HawkerClosureFeature
from features_location import LocationPlanner
from features_reviews import ReviewFeature

Coord = Tuple[float, float]


def print_banner() -> None:
    print("\n" + "=" * 60)
    print("        WELCOME TO HAWKER CENTER GUIDE")
    print("=" * 60)


def auth_menu() -> str:
    print("\n=== Account ===")
    print("1) Create Account")
    print("2) Login")
    print("0) Exit")
    return input("Choose: ").strip()


def main_menu() -> str:
    print("\n=== Main Menu ===")
    print("1) Browse Menu & Get Recommendations (Cuisine)")
    print("2) Price Filter Recommendations")
    print("3) Hawker Centre Closure Checker")
    print("4) Plan Your Visit (Location & Itinerary)")
    print("5) Reviews")
    print("0) Logout")
    return input("Choose: ").strip()


def reviews_menu() -> str:
    print("\n=== Reviews ===")
    print("1) Show top stalls (by bayes score)")
    print("2) Read reviews for a stall")
    print("3) Write a review")
    print("4) Mark a review helpful")
    print("0) Back")
    return input("Choose: ").strip()


def ask_for_location(planner: LocationPlanner) -> Optional[Coord]:
    """
    Runs once after login to store a session starting point.
    Returns (lat, lng) or None if user skips.
    """
    print("\n=== Set Your Location ===")
    print("This helps us estimate walking time and suggest nearby options.")
    print("You can skip this and set it later.\n")

    while True:
        raw = input("Enter your current postal code/address (or press Enter to skip): ").strip()
        if not raw:
            return None

        coords = planner.get_coords(raw)
        if coords:
            print(f"✅ Location saved: ({coords[0]:.6f}, {coords[1]:.6f})")
            return coords

        print("Could not recognize that location. Try again, or press Enter to skip.")


def run_cuisine_flow(handler: CuisineFeatureHandler, username: str) -> None:
    prefs = handler.load_preferences(username) or CuisinePreferences()

    print("\n=== Cuisine Preferences ===")
    print("Press Enter to skip any section.\n")

    edit = input("Do you want to update your cuisine/allergen preferences now? (Y/N): ").strip().lower()
    if edit in ("y", "yes"):
        available_cuisines = handler.get_available_cuisines()
        available_allergens = handler.get_available_allergens()

        print("\nAvailable cuisines (examples):")
        print(", ".join(available_cuisines[:20]) + (" ..." if len(available_cuisines) > 20 else ""))

        raw_cuisines = input("Preferred cuisines (comma-separated): ").strip()
        if raw_cuisines:
            prefs.cuisines = [x.strip() for x in raw_cuisines.split(",") if x.strip()]

        print("\nCommon allergens (examples):")
        print(", ".join(available_allergens[:20]) + (" ..." if len(available_allergens) > 20 else ""))

        raw_all = input("Allergens to avoid (comma-separated): ").strip()
        if raw_all:
            prefs.allergens_to_avoid = [x.strip() for x in raw_all.split(",") if x.strip()]

        handler.save_preferences(prefs, username)

    df = handler.filter(prefs)
    handler.display(df)


def run_closure_flow(closure: HawkerClosureFeature) -> None:
    print("\n=== Hawker Centre Closure Checker ===")
    print("Enter your trip dates in dd/mm/yyyy (example: 09/08/2026)")
    start = input("Trip start date (dd/mm/yyyy): ").strip()
    end = input("Trip end date (dd/mm/yyyy): ").strip()

    open_hcs = closure.get_open_hawker_centres(start, end)

    try:
        import pandas as pd
        if isinstance(open_hcs, (pd.DataFrame, pd.Series)):
            if open_hcs.empty:
                print("\nNo open hawker centres found for that range (or invalid dates).")
                return
            print(f"\nOpen hawker centres between {start} and {end}:")
            if hasattr(open_hcs, "columns") and "name" in open_hcs.columns:
                names = open_hcs["name"].dropna().unique().tolist()
                for i, name in enumerate(names, 1):
                    print(f"{i}. {name}")
            else:
                print(open_hcs.head(30).to_string(index=False))
            return
    except Exception:
        pass

    if open_hcs is None or (isinstance(open_hcs, list) and len(open_hcs) == 0):
        print("\nNo open hawker centres found for that range (or invalid dates).")
        return

    print(f"\nOpen hawker centres between {start} and {end}:")
    for i, name in enumerate(open_hcs, 1):
        print(f"{i}. {name}")


def run_location_flow(planner: LocationPlanner, session_start_coords: Optional[Coord]) -> None:
    print("\n=== Location & Itinerary Planner ===")
    planner.run_interactive(start_coords=session_start_coords)


def run_reviews_flow(reviews: ReviewFeature, username: str) -> None:
    while True:
        c = reviews_menu()
        if c == "0":
            return

        if c == "1":
            try:
                n = int(input("How many top stalls to show? (e.g. 10): ").strip() or "10")
            except ValueError:
                n = 10
            top_df = reviews.get_top_stalls(n=n)
            if top_df.empty:
                print("No stall data found.")
            else:
                print(top_df.to_string(index=False))

        elif c == "2":
            stall = input("Enter stall name (exact or close): ").strip()
            if not stall:
                continue
            df = reviews.find_reviews_by_stall_name(stall)
            if df.empty:
                print("No reviews found for that stall name.")
            else:
                print(df[["review_id", "user_name", "rating", "review_date", "helpful_count", "review_text"]]
                      .to_string(index=False))

        elif c == "3":
            stall = input("Stall name: ").strip()
            if not stall:
                continue
            rating = input("Rating (0-5): ").strip()
            text = input("Your review: ").strip()
            if not text:
                print("Review text cannot be empty.")
                continue
            try:
                review_id = reviews.add_review(stall_name=stall, rating=float(rating), review_text=text, user_name=username)
                print(f"✅ Review submitted! (review_id={review_id})")
            except Exception as e:
                print(f"❌ Could not add review: {e}")

        elif c == "4":
            rid = input("Enter review_id to mark helpful: ").strip()
            try:
                reviews.mark_review_helpful(int(rid))
            except Exception as e:
                print(f"❌ Could not mark helpful: {e}")

        else:
            print("Invalid choice.")


def main() -> None:
    print_banner()

    da = saachees_file.TouristProfileDA()

    cuisine_handler = CuisineFeatureHandler()
    closure_feature = HawkerClosureFeature()
    location_planner = LocationPlanner()
    reviews_feature = ReviewFeature()
    merged_pricing_df = load_default_merged_dataset()

    current_user: Optional[saachees_file.TouristProfile] = None
    session_start_coords: Optional[Coord] = None

    while True:
        if current_user is None:
            c = auth_menu()

            if c == "1":
                created = saachees_file.create_account(da)
                if created:
                    auto = input("Login now? (Y/N): ").strip().lower()
                    if auto in ("y", "yes"):
                        current_user = saachees_file.login(da)

            elif c == "2":
                current_user = saachees_file.login(da)

            elif c == "0":
                print("Bye!")
                return
            else:
                print("Invalid choice.")
                continue

            # After login, ask for location once per session
            if current_user is not None:
                session_start_coords = ask_for_location(location_planner)

            continue

        print(f"\nLogged in as: {current_user.username}")
        choice = main_menu()

        if choice == "1":
            run_cuisine_flow(cuisine_handler, current_user.username)
        elif choice == "2":
            run_pricing_filter(merged_pricing_df)
        elif choice == "3":
            run_closure_flow(closure_feature)
        elif choice == "4":
            run_location_flow(location_planner, session_start_coords)
        elif choice == "5":
            run_reviews_flow(reviews_feature, current_user.username)
        elif choice == "0":
            print("Logged out.")
            current_user = None
            session_start_coords = None
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()