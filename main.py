from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import saachees_file
from feature_cuisines import CuisineFeatureHandler, CuisinePreferences
from feature_pricing import PriceFeatureHandler
from features_closure import HawkerClosureFeature
from features_location import LocationPlanner
from features_reviews import ReviewFeature

Coord = Tuple[float, float]


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
    print("2) Price Filter Recommendations")
    print("3) Itinerary Planner")
    print("4) Reviews")
    print("5) Update Location / Trip Dates")
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


def run_cuisine_flow(
    handler: CuisineFeatureHandler,
    da: saachees_file.TouristProfileDA,
    username: str,
    session: SessionContext,
) -> None:
    prefs = handler.load_preferences(username) or CuisinePreferences()

    print("\n=== Browse Menu & Get Recommendations ===")
    print("Enter your cuisine preferences again for this search.")
    available = handler.get_available_cuisines()
    if available:
        preview = ", ".join(available[:20])
        if len(available) > 20:
            preview += " ..."
        print(f"Available cuisines: {preview}")

    raw_c = input("Cuisine preferences (comma-separated): ").strip()
    if raw_c:
        prefs.cuisines = [x.strip() for x in raw_c.split(",") if x.strip()]
        handler.save_preferences(prefs, username)

    top = handler.get_top_nearby_stalls(
        prefs,
        coords=session.coords,
        radius_km=session.radius_km,
        top_n=5,
        m=20.0,
        trip_start=session.trip_start,
        trip_end=session.trip_end,
    )

    if top.empty:
        print("\nNo stalls matched your preferences.")
        return

    _print_stall_cards(top)

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

        menu = handler.get_menu_for_stall(stall_id, prefs)
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


def run_pricing_flow(
    handler: PriceFeatureHandler,
    da: saachees_file.TouristProfileDA,
    username: str,
    session: SessionContext,
) -> None:
    print("\n=== Price Filter Recommendations ===")
    try:
        min_price = float(input("Enter minimum price: ").strip())
        max_price = float(input("Enter maximum price: ").strip())
    except ValueError:
        print("Please enter valid numeric prices.")
        return

    pref = input("Food (F), Drinks (D), or Both (B)? ").strip().upper()
    if pref not in {"F", "D", "B"}:
        print("Invalid preference.")
        return

    top = handler.get_top_price_recommendations(
        min_price=min_price,
        max_price=max_price,
        preference=pref,
        coords=session.coords,
        radius_km=session.radius_km,
        top_n=5,
        trip_start=session.trip_start,
        trip_end=session.trip_end,
    )

    if top.empty:
        print("\nNo stalls matched that price range.")
        return

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
        menu = handler.get_menu_for_stall(stall_id)

        print("\n" + "=" * 70)
        print(f"Menu for: {stall_name}")
        print("=" * 70)
        if menu.empty:
            print("No menu items found.")
        else:
            cols = [c for c in ["item_name", "price"] if c in menu.columns]
            print(menu[cols].to_string(index=False))

        add = input(f"\nAdd '{stall_name}' to your itinerary? (Y/N): ").strip().lower()
        if add in ("y", "yes"):
            da.add_saved_stall(username, stall_id, hawker_id)
            print(f"Saved: {stall_name} @ {hawker_name}")
        print()


def run_itinerary_flow(
    cuisine_handler: CuisineFeatureHandler,
    da: saachees_file.TouristProfileDA,
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
                print(df[["review_id", "user_name", "rating", "review_date", "helpful_count", "review_text"]].to_string(index=False))
        elif c == "3":
            stall = input("Stall name: ").strip()
            rating = input("Rating (0-5): ").strip()
            text = input("Your review: ").strip()
            if not stall or not text:
                print("Please enter both the stall name and review text.")
                continue
            try:
                review_id = reviews.add_review(stall_name=stall, rating=float(rating), review_text=text, user_name=username)
                print(f"Review submitted! (review_id={review_id})")
            except Exception as e:
                print(f"Could not add review: {e}")
        elif c == "4":
            rid = input("Enter review_id to mark helpful: ").strip()
            try:
                reviews.mark_review_helpful(int(rid))
            except Exception as e:
                print(f"Could not mark helpful: {e}")
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

    da = saachees_file.TouristProfileDA()
    cuisine_handler = CuisineFeatureHandler()
    pricing_handler = PriceFeatureHandler()
    location_planner = LocationPlanner()
    reviews_feature = ReviewFeature()

    current_user: Optional[saachees_file.TouristProfile] = None
    session = SessionContext()

    while True:
        if current_user is None:
            c = auth_menu()
            if c == "1":
                created = saachees_file.create_account(da)
                if created:
                    auto = input("\nLogin now? (Y/N): ").strip().lower()
                    if auto in ("y", "yes"):
                        current_user = saachees_file.login(da)
                        if current_user:
                            setup_trip_context(location_planner, session)
            elif c == "2":
                current_user = saachees_file.login(da)
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
            run_cuisine_flow(cuisine_handler, da, current_user.username, session)
        elif choice == "2":
            run_pricing_flow(pricing_handler, da, current_user.username, session)
        elif choice == "3":
            run_itinerary_flow(cuisine_handler, da, location_planner, current_user.username, session)
        elif choice == "4":
            run_reviews_flow(reviews_feature, current_user.username)
        elif choice == "5":
            update_trip_context(location_planner, session)
        elif choice == "0":
            print("Logged out.")
            current_user = None
            session = SessionContext()
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()