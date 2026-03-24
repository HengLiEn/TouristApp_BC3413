from flask import Flask, render_template, request, redirect, url_for, session, flash
from typing import Optional
from feature_cuisines import CuisineFeatureHandler, CuisinePreferences
from feature_onboarding import TouristProfileDA
from features_location import LocationPlanner
from datetime import datetime
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
    selected_cuisine  = request.args.get('cuisine', None)
    selected_stars    = request.args.get('stars', None)
    selected_sort     = request.args.get('sort', 'score')
    search_query      = request.args.get('q', '').strip().lower()
    selected_allergens = request.args.getlist('allergens')  # e.g. ['gluten', 'dairy']

    handler = CuisineFeatureHandler()

    prefs = CuisinePreferences()
    stalls_df = handler.get_top_nearby_stalls(prefs=prefs, coords=None, top_n=50)
    stalls_list = stalls_df.to_dict(orient='records')

    cuisines = handler.get_available_cuisines()

    # Filter by cuisine
    if selected_cuisine:
        stalls_list = [
            s for s in stalls_list
            if s.get('cuisine_type', '').lower() == selected_cuisine
        ]

    # Filter by stars
    if selected_stars:
        stalls_list = [
            s for s in stalls_list
            if s.get('avg_rating', 0) >= float(selected_stars)
        ]

    # Filter by search query (stall name or hawker centre name)
    if search_query:
        stalls_list = [
            s for s in stalls_list
            if search_query in s.get('stall_name', '').lower()
            or search_query in s.get('hawker_name', '').lower()
        ]

    # Filter by allergens — exclude stalls that contain any selected allergen
    # Expects each stall record to have an 'allergens' field: a list of strings
    # e.g. ['gluten', 'shellfish']
    if selected_allergens:
        def stall_is_safe(stall):
            stall_allergens = [a.lower() for a in stall.get('allergens', [])]
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

    return render_template('feature_cuisines.html',
        stalls=stalls_list,
        cuisines=cuisines,
        selected_cuisine=selected_cuisine,
        selected_stars=selected_stars,
        selected_sort=selected_sort,
        search_query=search_query,
        selected_allergens=selected_allergens,
    )
@app.route("/pricing")
def pricing():
    return render_template("pricing.html")

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

# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True)