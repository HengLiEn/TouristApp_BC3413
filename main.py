"""
main.py — UX cleanup
Changes:
- "=== Account ===" -> "=== Account Page ==="
- Remove "Logged in as: <username>"
- Cuisine feature asks for location inside itself (as requested)
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
    print("\n=== Account Page ===")
    print("1) Create Account")
    print("2) Login")
    print("0) Exit")
    return input("Choose: ").strip()


def main_menu() -> str:
    print("\n=== Main Menu ===")
    print("1) Browse Menu & Get Recommendations")
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


def ask_location_and_radius_for_feature(planner: LocationPlanner) -> tuple[Optional[Coord], float]:
    print("\n=== Use Nearby Filtering ===")
    print("This will show stalls close to you first.")
    use = input("Use location filtering? (Y/N): ").strip().lower()
    if use not in ("y", "yes"):
        print("Nearby filtering: OFF")
        return None, 2.0

    coords: Optional[Coord] = None
    while True:
        raw = input("Enter your postal code/address (e.g., '560101' or 'Bedok'): ").strip()
        if not raw:
            print("No location entered. Nearby filtering OFF.")
            return None, 2.0

        coords = planner.get_coords(raw)
        if coords:
            print(f"✅ Location set: ({coords[0]:.6f}, {coords[1]:.6f})")
            break
        print("Could not recognize that location. Try again (or press Enter to cancel).")

    radius_km = 2.0
    raw_r = input("Nearby radius in km (default 2): ").strip()
    if raw_r:
        try:
            radius_km = max(0.1, float(raw_r))
        except ValueError:
            radius_km = 2.0

    print(f"Nearby filtering: ON (within {radius_km:g} km)")
    return coords, radius_km


def run_cuisine_flow(
    handler: CuisineFeatureHandler,
    username: str,
    planner: LocationPlanner,
    session_coords: Optional[Coord],
    session_radius_km: float,
) -> tuple[Optional[Coord], float]:
    prefs = handler.load_preferences(username) or CuisinePreferences()

    print("\n=== Browse Menu & Get Recommendations ===")
    print("Press Enter to skip any section.")

    # 1) Update preferences
    edit = input("\nDo you want to update your cuisine preferences now? (Y/N): ").strip().lower()
    if edit in ("y", "yes"):
        cuisines = handler.get_available_cuisines()
        allergens = handler.get_available_allergens()

        print("Available cuisines (examples):")
        print(", ".join(cuisines[:20]) + (" ..." if len(cuisines) > 20 else ""))

        raw_c = input("Preferred cuisines (comma-separated): ").strip()
        if raw_c:
            prefs.cuisines = [x.strip() for x in raw_c.split(",") if x.strip()]
        handler.save_preferences(prefs, username)

    # 2) Ask location/radius inside this feature
    if session_coords is None:
        session_coords, session_radius_km = ask_location_and_radius_for_feature(planner)
    else:
        print("\n=== Nearby Filtering (Current) ===")
        print(f"Current saved location: ({session_coords[0]:.6f}, {session_coords[1]:.6f})")
        print(f"Current radius: {session_radius_km:g} km")
        change = input("Change location/radius for this session? (Y/N): ").strip().lower()
        if change in ("y", "yes"):
            session_coords, session_radius_km = ask_location_and_radius_for_feature(planner)

    # 3) Recommend top 5 stalls
    top = handler.get_top_nearby_stalls(
        prefs,
        coords=session_coords,
        radius_km=session_radius_km,
        top_n=5,
        m=20.0,
    )

    if top.empty:
        print("\nNo stalls matched your preferences.")
        print("Try: increasing radius, removing allergens, or choosing a different cuisine.\n")
        return session_coords, session_radius_km

    print("\nTop Recommended Stalls:")
    print("-" * 70)
    for i, row in top.iterrows():
        stall = row.get("stall_name", "Unknown stall")
        hawker = row.get("hawker_name", "Unknown hawker centre")
        dist = row.get("distance_km", None)
        bayes = float(row.get("bayes_score", 0.0) or 0.0)
        avg = float(row.get("avg_rating", 0.0) or 0.0)
        n = int(row.get("n_reviews", 0) or 0)

        dist_txt = f"{float(dist):.2f} km" if dist is not None and str(dist) != "nan" else "N/A"
        print(f"[{i+1}] {stall}  @  {hawker}")
        print(f"     Distance: {dist_txt} | Average Rating: {avg:.2f} | No. of Reviews: {n}\n")

    # 4) Drill-down into menu items
    while True:
        choice = input("Enter stall number to view its menu (or 0 to go back): ").strip()
        if choice == "0":
            return session_coords, session_radius_km
        if not choice.isdigit():
            print("Please enter a number.")
            continue

        idx = int(choice) - 1
        if idx < 0 or idx >= len(top):
            print("Invalid stall number.")
            continue

        stall_id = int(top.loc[idx, "stall_id"])
        stall_name = top.loc[idx, "stall_name"]
        hawker_name = top.loc[idx, "hawker_name"]

        menu = handler.get_menu_for_stall(stall_id, prefs)

        print("\n" + "=" * 70)
        print(f"Menu for: {stall_name}")
        print("=" * 70)

        if menu.empty:
            print("No menu items found (or all removed due to allergen filters).")
            continue

        cols = [c for c in ["item_name", "price"] if c in menu.columns]
        show_n = 20
        print(menu[cols].head(show_n).to_string(index=False))

        if len(menu) > show_n:
            more = input(f"\nShow all {len(menu)} items? (Y/N): ").strip().lower()
            if more in ("y", "yes"):
                print("\n" + menu[cols].to_string(index=False))

        print()


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


def run_location_flow(planner: LocationPlanner, coords: Optional[Coord]) -> None:
    print("\n=== Location & Itinerary Planner ===")
    planner.run_interactive(start_coords=coords)


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

    # These constructors used to print "Loaded ..." — we removed those prints in their files.
    cuisine_handler = CuisineFeatureHandler()
    closure_feature = HawkerClosureFeature()
    location_planner = LocationPlanner()
    reviews_feature = ReviewFeature()

    merged_pricing_df = load_default_merged_dataset()

    current_user: Optional[saachees_file.TouristProfile] = None

    # Session location info (set from inside Cuisine feature)
    session_coords: Optional[Coord] = None
    session_radius_km: float = 2.0

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

            continue

        # NOTE: removed "Logged in as: ..."
        choice = main_menu()

        if choice == "1":
            session_coords, session_radius_km = run_cuisine_flow(
                cuisine_handler,
                current_user.username,
                location_planner,
                session_coords,
                session_radius_km,
            )

        elif choice == "2":
            run_pricing_filter(merged_pricing_df)

        elif choice == "3":
            run_closure_flow(closure_feature)

        elif choice == "4":
            run_location_flow(location_planner, session_coords)

        elif choice == "5":
            run_reviews_flow(reviews_feature, current_user.username)

        elif choice == "0":
            print("Logged out.")
            current_user = None
            session_coords = None
            session_radius_km = 2.0

        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()