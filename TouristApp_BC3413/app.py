from flask import Flask, render_template, request, redirect, url_for, session, flash
from typing import Optional
import re
from feature_cuisines import CuisineFeatureHandler, CuisinePreferences
from feature_onboarding import TouristProfileDA
from features_location import LocationPlanner
from datetime import datetime, timedelta
from collections import Counter
import pandas as pd
# from functools import wraps
import os
# import sqlite3

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"))
app.secret_key = "bc3413-secret"

# DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tourist_profiles.db")

# def get_db():
#     conn = sqlite3.connect(DB_PATH)
#     conn.row_factory = sqlite3.Row
#     return conn

# def login_required(f):
#     @wraps(f)
#     def decorated(*args, **kwargs):
#         if "username" not in session:
#             flash("Please log in first.")
#             return redirect(url_for("login"))
#         return f(*args, **kwargs)
#     return decorated

# @app.route("/", methods=["GET", "POST"])
# @app.route("/login", methods=["GET", "POST"])
# def login():
#     if request.method == "POST":
#         username = request.form["username"]
#         password = request.form["password"]
#         conn = get_db()
#         user = conn.execute(
#             "SELECT * FROM tourist_profiles WHERE username = ? AND password = ?",
#             (username, password)
#         ).fetchone()
#         conn.close()
#         if user:
#             session["username"] = username
#             return redirect(url_for("dashboard"))
#         else:
#             flash("Invalid username or password.")
#     return render_template("login.html")

# @app.route("/logout")
# def logout():
#     session.clear()
#     return redirect(url_for("login"))

# @app.route("/dashboard")
# def dashboard():
#     return render_template("dashboard.html", username=session["username"])

# ── Cuisines (ACTIVE) ─────────────────────────────────────────────────────────
@app.route('/cuisines')
def cuisines():
    selected_cuisine = request.args.get('cuisine', None)
    selected_stars = request.args.get('stars', None)
    selected_sort = request.args.get('sort', 'score')
    search_query = request.args.get('q', '').strip().lower()
    selected_allergens = request.args.getlist('allergens')  # e.g. ['gluten', 'dairy']
    max_price = request.args.get('max_price', 15, type=float)  # slider: $1–$15, default = show all

    handler = CuisineFeatureHandler()

    stalls_df = handler._stall_base()
    stalls_df = stalls_df.merge(handler._get_review_scores(), on='stall_id', how='left')
    stalls_df['n_reviews'] = stalls_df['n_reviews'].fillna(0).astype(int)
    stalls_df['avg_rating'] = stalls_df['avg_rating'].fillna(0.0)
    stalls_df['bayes_score'] = stalls_df['bayes_score'].fillna(0.0)

    per_cuisine = (
        stalls_df.groupby('cuisine_type', group_keys=False)
                 .apply(lambda g: g.sample(min(len(g), 1), random_state=42))
    )

    remaining = (
        stalls_df[~stalls_df['stall_id'].isin(per_cuisine['stall_id'])]
        .sort_values('bayes_score', ascending=False)
    )
    slots_left = max(0, 50 - len(per_cuisine))
    filler = remaining.head(slots_left)

    varied = pd.concat([per_cuisine, filler]).sample(frac=1, random_state=42).head(50)
    stalls_list = varied.to_dict(orient='records')

    cuisines_list = handler.get_available_cuisines()

    # Filter by cuisine
    if selected_cuisine:
        stalls_list = [
            s for s in stalls_list
            if s.get('cuisine_type', '').lower() == selected_cuisine
        ]

    # Filter by stars
    if selected_stars:
        min_stars = float(selected_stars)
        if min_stars == 5.0:
            stalls_list = [s for s in stalls_list if s.get('avg_rating', 0) == 5.0]
        else:
            max_stars = min_stars + 0.9
            stalls_list = [s for s in stalls_list if min_stars <= s.get('avg_rating', 0) <= max_stars]

    # Filter by search query (stall name or hawker centre name)
    if search_query:
        stalls_list = [
            s for s in stalls_list
            if search_query in s.get('stall_name', '').lower()
               or search_query in s.get('hawker_name', '').lower()
        ]

    # Filter by allergens - exclude stalls that contain any selected allergen
    # Expects each stall record to have an 'allergens' field: a list of strings
    # e.g. ['gluten', 'shellfish']
    if selected_allergens:
        def stall_is_safe(stall):
            raw = stall.get('allergens', '')
            if isinstance(raw, list):
                stall_allergens = [a.lower().strip() for a in raw]
            else:
                stall_allergens = [a.lower().strip() for a in re.split(r'[,;|/]+', str(raw)) if a.strip()]
            return not any(a in stall_allergens for a in selected_allergens)

        stalls_list = [s for s in stalls_list if stall_is_safe(s)]

    # Sort
    if selected_sort == 'rating':
        stalls_list.sort(key=lambda x: x.get('avg_rating', 0), reverse=True)
    elif selected_sort == 'reviews':
        stalls_list.sort(key=lambda x: x.get('n_reviews', 0), reverse=True)
    elif selected_sort == 'distance':
        stalls_list.sort(key=lambda x: x.get('distance_km', 999))
    else:
        stalls_list.sort(key=lambda x: x.get('bayes_score', 0), reverse=True)

    # Cap at 50 hawker stalls
    stalls_list = stalls_list[:50]

    return render_template('feature_cuisines.html',
                           stalls=stalls_list,
                           cuisines=cuisines_list,
                           selected_cuisine=selected_cuisine,
                           selected_stars=selected_stars,
                           selected_sort=selected_sort,
                           search_query=search_query,
                           selected_allergens=selected_allergens,
                           max_price=max_price,
                           )

# ------ PRICING -------
@app.route("/pricing")
def pricing():
    stall_id = request.args.get('stall_id', type=int)

    if not stall_id:
        return render_template("feature_pricing.html",
                               stall=None, menu_items=[], error="No stall selected.")

    handler = CuisineFeatureHandler()

    # Stall header info
    stall_base = handler._stall_base()
    scores = handler._get_review_scores()
    stall_row = stall_base.merge(scores, on='stall_id', how='left')
    stall_row = stall_row[stall_row['stall_id'] == stall_id]

    if stall_row.empty:
        return render_template("feature_pricing.html",
                               stall=None, menu_items=[], error="Stall not found.")

    import pandas as pd
    stall = stall_row.iloc[0].to_dict()

    # Sanitise every value so NaN floats never reach Jinja
    stall = {k: (None if (isinstance(v, float) and pd.isna(v)) else v) for k, v in stall.items()}
    stall['n_reviews']  = int(stall.get('n_reviews',  0) or 0)
    stall['avg_rating'] = float(stall.get('avg_rating', 0.0) or 0.0)

    # Menu items for this stall
    try:
        menu_df = handler.get_menu_for_stall(stall_id)
    except Exception:
        menu_df = pd.DataFrame()

    def _safe_str(val):
        if val is None:
            return ''
        try:
            if pd.isna(val):
                return ''
        except (TypeError, ValueError):
            pass
        return str(val).strip()

    def _parse_allergens(raw):
        s = _safe_str(raw).lower()
        if not s or s in ('nan', 'none'):
            return []
        return [a.strip() for a in re.split(r'[,;|/]+', s) if a.strip()]

    # Allergens the user wants to avoid
    blocked_allergens = [a.lower().strip() for a in request.args.getlist('allergens')]

    # Max price cap forwarded from the cuisines filters
    max_price = request.args.get('max_price', 15, type=float)

    menu_items = []
    for _, row in menu_df.iterrows():
        price_raw = row.get('price')
        try:
            price = float(price_raw) if pd.notna(price_raw) else None
        except (ValueError, TypeError):
            price = None

        item_allergens = _parse_allergens(row.get('allergens', ''))

        # Skip this item if it contains any allergen the user is avoiding
        if blocked_allergens and any(a in item_allergens for a in blocked_allergens):
            continue

        # Skip this item if its price exceeds the user's max price
        if price is not None and max_price < 15 and price > max_price:
            continue

        menu_items.append({
            'item_name': _safe_str(row.get('item_name')) or '—',
            'price': price,
            'allergens': item_allergens,
            'description': _safe_str(row.get('description', '')),
        })

    # Pass active filters back so the Back link can restore them
    back_params = {
        'cuisine':   request.args.get('cuisine', ''),
        'stars':     request.args.get('stars', ''),
        'sort':      request.args.get('sort', ''),
        'q':         request.args.get('q', ''),
        'max_price': request.args.get('max_price', 15),
        'allergens': request.args.getlist('allergens'),
    }

    return render_template("feature_pricing.html",
                           stall=stall,
                           menu_items=menu_items,
                           error=None,
                           back_params=back_params)

da = TouristProfileDA()           # one shared instance
planner = LocationPlanner()       # one shared instance

"""
    Renders the Update Location & Dates page.
    Reads the current saved values from the DB (via Flask session username)
    and passes them to the template so the status bar and form fields are
    pre-filled.
    """
@app.route("/location")
def location():
    # TEMPORARY — remove this block once Saachee's login is ready
    session["username"] = "test_user"

    # TEMPORARY — create a dummy profile if it doesn't exist
    if not da.get_profile("test_user"):
        from feature_onboarding import TouristProfile
        da.insert_profile(TouristProfile(
            username="test_user", password="test",
            name="Test", country="SG", spice_level=2,
            allergens=[], preferred_cuisines=[],
            created_at=datetime.now().isoformat()
        ))

    # if "username" not in session:
    #     flash("Please log in first.", "error")
    #     return redirect(url_for("login"))

    profile = da.get_profile(session["username"])

    # Coordinates — tuple or None
    current_coords = None
    if profile and profile.location_lat is not None and profile.location_lng is not None:
        current_coords = (float(profile.location_lat), float(profile.location_lng))

    # Trip dates stored as dd/mm/yyyy in DB — convert to ISO (yyyy-mm-dd) for
    # the HTML date input's value attribute
    trip_start_iso = _ddmmyyyy_to_iso(profile.trip_start) if profile else None
    trip_end_iso   = _ddmmyyyy_to_iso(profile.trip_end)   if profile else None

    return render_template(
        "feature_location.html",
        active_page      = "location",
        current_coords   = current_coords,
        current_address  = session.get("last_address"),   # remembered across request
        current_radius   = float(profile.radius_km) if profile and profile.radius_km else 2.0,
        current_trip_start = profile.trip_start if profile else None,
        current_trip_end   = profile.trip_end   if profile else None,
        trip_start_iso   = trip_start_iso,
        trip_end_iso     = trip_end_iso,
    )


@app.route("/location/update-location", methods=["POST"])
def update_location():
    """
    Handles the Update Location form submission.
    - Calls OneMap via LocationPlanner.get_coords() to resolve address → coords
    - Saves updated coords + radius to the DB
    - Redirects back to /location
    """
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    address   = request.form.get("address", "").strip()
    radius_km = float(request.form.get("radius_km", 2.0))

    if not address:
        flash("Please enter a postal code or address.", "error")
        return redirect(url_for("location"))

    coords = planner.get_coords(address)

    if not coords:
        flash(f"Could not find '{address}' on OneMap. Please try a different address or postal code.", "error")
        return redirect(url_for("location"))

    # Remember the address text so the input stays filled after redirect
    session["last_address"] = address

    # Load existing trip dates so we don't overwrite them
    profile = da.get_profile(session["username"])
    trip_start = profile.trip_start if profile else None
    trip_end   = profile.trip_end   if profile else None

    da.update_trip_context(
        username  = session["username"],
        coords    = coords,
        radius_km = radius_km,
        trip_start = trip_start,
        trip_end   = trip_end,
    )

    flash(f"Location updated to ({coords[0]:.5f}, {coords[1]:.5f}).", "success")
    return redirect(url_for("location"))


@app.route("/location/update-dates", methods=["POST"])
def update_trip_dates():
    """
    Handles the Update Trip Dates form submission.
    - HTML date inputs give yyyy-mm-dd; we convert to dd/mm/yyyy to match the
      format used everywhere else in the project (hawker_filter, main.py, etc.)
    - Saves updated dates to the DB without touching coords/radius
    """
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    start_iso = request.form.get("trip_start", "").strip()
    end_iso   = request.form.get("trip_end",   "").strip()

    # Both must be provided together
    if not start_iso or not end_iso:
        flash("Please enter both a start and end date.", "error")
        return redirect(url_for("location"))

    # Convert yyyy-mm-dd → dd/mm/yyyy
    try:
        trip_start = _iso_to_ddmmyyyy(start_iso)
        trip_end   = _iso_to_ddmmyyyy(end_iso)
    except ValueError:
        flash("Invalid date format. Please use the date picker.", "error")
        return redirect(url_for("location"))

    # Validate start is not after end
    start_dt = datetime.strptime(trip_start, "%d/%m/%Y")
    end_dt   = datetime.strptime(trip_end,   "%d/%m/%Y")
    if start_dt > end_dt:
        flash("Start date must be before or on the same day as end date.", "error")
        return redirect(url_for("location"))

    # Load existing coords so we don't overwrite them
    profile = da.get_profile(session["username"])
    coords = None
    if profile and profile.location_lat is not None and profile.location_lng is not None:
        coords = (float(profile.location_lat), float(profile.location_lng))
    radius_km = float(profile.radius_km) if profile and profile.radius_km else 2.0

    da.update_trip_context(
        username   = session["username"],
        coords     = coords,
        radius_km  = radius_km,
        trip_start = trip_start,
        trip_end   = trip_end,
    )

    flash(f"Trip dates saved: {trip_start} → {trip_end}", "success")
    return redirect(url_for("location"))


# ── Itinerary  ─────
# These routes expect:
#   da.get_saved_stalls(username)  → list of stall_ids
#   da.add_saved_stall(username, stall_id)
#   da.remove_saved_stall(username, stall_id)
#   da.clear_saved_stalls(username)
#   handler.get_stalls_by_ids(stall_ids, ...) → DataFrame

@app.route("/itinerary/save/<int:stall_id>")  # needs a button incorporated in feature_pricing.html
def itinerary_save(stall_id):
    session["username"] = "test_user"  # TEMP
    da.add_saved_stall(session["username"], stall_id)
    flash("Stall saved to your itinerary!", "success")
    return redirect(request.referrer or url_for("cuisines"))


@app.route("/itinerary")
def itinerary():
    # TEMPORARY — remove once login is ready
    session["username"] = "test_user"

    profile = da.get_profile(session["username"])
    saved_ids = da.get_saved_stalls(session["username"])

    # Resolve stall details
    handler = CuisineFeatureHandler()
    itinerary_list = []
    if saved_ids:
        coords = None
        radius_km = 5.0
        trip_start = trip_end = None
        if profile:
            if profile.location_lat and profile.location_lng:
                coords = (float(profile.location_lat), float(profile.location_lng))
            if profile.radius_km:
                radius_km = float(profile.radius_km)
            trip_start = profile.trip_start
            trip_end = profile.trip_end

        stalls_df = handler.get_stalls_by_ids(
            saved_ids,
            coords=coords,
            radius_km=max(radius_km, 5.0),  # widen radius for itinerary
            trip_start=trip_start,
            trip_end=trip_end,
        )
        scores_df = handler._get_review_scores()
        if not stalls_df.empty and not scores_df.empty:
            stalls_df = stalls_df.merge(scores_df, on='stall_id', how='left')

        stalls_df['n_reviews'] = stalls_df['n_reviews'].fillna(0).astype(int) if 'n_reviews' in stalls_df.columns else 0
        stalls_df['avg_rating'] = stalls_df['avg_rating'].fillna(0.0) if 'avg_rating' in stalls_df.columns else 0.0

        # Preserve saved order
        id_order = {sid: i for i, sid in enumerate(saved_ids)}
        stalls_df['_order'] = stalls_df['stall_id'].map(id_order)
        stalls_df = stalls_df.sort_values('_order').drop(columns=['_order'])

        for _, row in stalls_df.iterrows():
            d = row.to_dict()
            d = {k: (None if isinstance(v, float) and pd.isna(v) else v) for k, v in d.items()}
            d['n_reviews'] = int(d.get('n_reviews', 0) or 0)
            d['avg_rating'] = float(d.get('avg_rating', 0.0) or 0.0)
            itinerary_list.append(d)

    # Build day-by-day structure if trip dates are set
    days = []
    days_count = 0
    trip_start = profile.trip_start if profile else None
    trip_end = profile.trip_end if profile else None

    if trip_start and trip_end and itinerary_list:
        try:
            start_dt = datetime.strptime(trip_start, "%d/%m/%Y")
            end_dt = datetime.strptime(trip_end, "%d/%m/%Y")
            days_count = (end_dt - start_dt).days + 1

            # Round-robin distribute stalls across days
            day_buckets = [[] for _ in range(days_count)]
            for i, stall in enumerate(itinerary_list):
                day_buckets[i % days_count].append(stall)

            WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            for d_idx, bucket in enumerate(day_buckets):
                cur_dt = start_dt + timedelta(days=d_idx)
                days.append({
                    "day_num": d_idx + 1,
                    "weekday": WEEKDAYS[cur_dt.weekday()],
                    "date_str": cur_dt.strftime("%d %b %Y"),
                    "stalls": bucket,
                })
        except ValueError:
            pass  # malformed dates — fall back to flat list

    # Cuisine breakdown
    cuisine_counts = Counter(
        s.get('cuisine_type', 'Other') or 'Other'
        for s in itinerary_list
    )
    cuisine_breakdown = cuisine_counts.most_common()

    # Avg rating
    ratings = [s['avg_rating'] for s in itinerary_list if s.get('avg_rating')]
    avg_rating = sum(ratings) / len(ratings) if ratings else None

    return render_template(
        "feature_itinerary.html",
        active_page="itinerary",
        itinerary=itinerary_list,
        days=days,
        days_count=days_count or 0,
        trip_start=trip_start,
        trip_end=trip_end,
        cuisines_count=len(cuisine_counts),
        cuisine_breakdown=cuisine_breakdown,
        avg_rating=avg_rating,
    )


@app.route("/itinerary/remove/<int:stall_id>")
def itinerary_remove(stall_id):
    session["username"] = "test_user"
    current = da.get_saved_stalls(session["username"])
    kept = [sid for sid in current if sid != stall_id]
    da.clear_saved_stalls(session["username"])
    for sid in kept:
        da.add_saved_stall(session["username"], sid)
    flash("Stall removed from your itinerary.", "success")
    return redirect(url_for("itinerary"))


@app.route("/itinerary/clear")
def itinerary_clear():
    session["username"] = "test_user"  # TEMP
    da.clear_saved_stalls(session["username"])
    flash("Itinerary cleared.", "success")
    return redirect(url_for("itinerary"))


@app.route("/itinerary/export")
def itinerary_export():
    """Simple plain-text export of saved stalls."""
    session["username"] = "test_user"  # TEMP

    profile = da.get_profile(session["username"])
    saved_ids = da.get_saved_stalls(session["username"])
    handler = CuisineFeatureHandler()

    lines = ["HAWKER HUNT — MY ITINERARY", "=" * 40]
    if profile and profile.trip_start:
        lines.append(f"Trip: {profile.trip_start} → {profile.trip_end}")
    lines.append("")

    if saved_ids:
        stalls_df = handler.get_stalls_by_ids(saved_ids, coords=None, radius_km=50)
        scores_df = handler._get_review_scores()
        if not stalls_df.empty and not scores_df.empty:
            stalls_df = stalls_df.merge(scores_df, on='stall_id', how='left')
        for i, (_, row) in enumerate(stalls_df.iterrows(), 1):
            lines.append(f"[{i}] {row.get('stall_name', '?')}")
            lines.append(f"    @ {row.get('hawker_name', '?')}")
            lines.append(
                f"    Rating: {float(row.get('avg_rating', 0) or 0):.1f} | Cuisine: {row.get('cuisine_type', '?')}")
            lines.append("")

    from flask import Response
    return Response(
        "\n".join(lines),
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=hawker_hunt_itinerary.txt"}
    )

# ── Private date-conversion helpers ──────────────────────────────────────────

def _iso_to_ddmmyyyy(iso_str: str) -> str:
    """Converts '2026-04-01' → '01/04/2026'"""
    dt = datetime.strptime(iso_str, "%Y-%m-%d")
    return dt.strftime("%d/%m/%Y")


def _ddmmyyyy_to_iso(ddmmyyyy_str) -> Optional[str]:
    """Converts '01/04/2026' → '2026-04-01'. Returns None for blank/invalid."""
    if not ddmmyyyy_str:
        return None
    try:
        dt = datetime.strptime(ddmmyyyy_str, "%d/%m/%Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None

@app.route("/closure")
def closure():
    return render_template('feature_onboarding.html', active_page='closure')

@app.route("/reviews")
def reviews():
    return render_template('feature_onboarding.html', active_page='reviews')

@app.route('/onboarding')
def onboarding():
    return render_template('feature_onboarding.html', active_page='onboarding')

if __name__ == "__main__":
    app.run(debug=True)
