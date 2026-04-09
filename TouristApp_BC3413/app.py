from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, jsonify
from typing import Optional
import re
from feature_cuisines import CuisineFeatureHandler, CuisinePreferences
from feature_onboarding import TouristProfileDA, TouristProfile
from features_location import LocationPlanner, haversine_km
from features_reviews import ReviewFeature
from features_closure import HawkerClosureFeature
from datetime import datetime, timedelta
import pandas as pd,json
import os
from collections import Counter
import sqlite3
from functools import wraps

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
CENTRES_CSV  = os.path.join(BASE_DIR, 'dataset', 'Hawker Centre Data', 'hawker_centers.csv')
CLOSURES_CSV = os.path.join(BASE_DIR, 'dataset', 'Hawker Centre Data', 'DatesofHawkerCentresClosure.csv')
MENU_CSV     = os.path.join(BASE_DIR, 'dataset', 'Multiple Stalls Menu and Data', 'menu_items.csv')
REVIEWS_CSV  = os.path.join(BASE_DIR, 'dataset', 'Multiple Stalls Menu and Data', 'reviews.csv')
STALLS_JSON  = os.path.join(BASE_DIR, 'dataset', 'Multiple Stalls Menu and Data', 'stalls.json')
STALLS_CSV = os.path.join(BASE_DIR, 'dataset', 'Multiple Stalls Menu and Data', 'stalls.csv')


app = Flask(__name__, template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"))
app.secret_key = "bc3413-secret"

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tourist_profiles.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            flash("Please log in first.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            flash("Please enter both username and password.", "error")
            return redirect(url_for("login"))

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM tourist_profiles WHERE username = ? AND password = ?",
            (username, password)
        ).fetchone()
        conn.close()

        if user:
            session["username"] = user["username"]
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "error")
        return redirect(url_for("login"))

    return render_template("login.html", active_page="login")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("landing"))

@app.route("/")
def landing():
    return render_template("landing_page.html", active_page="landing")

@app.route("/dashboard")
@login_required
def dashboard():
    hc   = pd.read_csv(CENTRES_CSV)
    cl   = pd.read_csv(CLOSURES_CSV)
    menu = pd.read_csv(MENU_CSV)
    rev  = pd.read_csv(REVIEWS_CSV)

    STALLS_CSV = os.path.join(BASE_DIR, 'dataset', 'Multiple Stalls Menu and Data', 'stalls.csv')
    stalls = pd.read_csv(STALLS_CSV)

    # Filter to food stalls only (exclude market types)
    MARKET_TYPES = {'Dry Goods', 'Hardware', 'Fruits', 'Seafood', 'Sundries',
                    'Poultry', 'Vegetables', 'Wet Market'}
    food_stalls = stalls[~stalls['cuisine_type'].isin(MARKET_TYPES)]

    # ── Stat cards ─────────────────────────────────────────────────
    total_stalls  = len(food_stalls)
    total_centres = len(cl)
    avg_price     = round(menu['price'].mean(), 2)
    avg_rating    = round(rev['rating'].mean(), 2)
    total_reviews = len(rev)

    # ── Bar: avg price per hawker centre (top 10) ──────────────────
    menu_stalls = menu.merge(stalls[['stall_id', 'hawker_center_id']], on='stall_id')
    menu_hc = menu_stalls.merge(
        hc[['center_id', 'center_name']],
        left_on='hawker_center_id', right_on='center_id'
    )
    price_by_centre = (
        menu_hc.groupby('center_name')['price']
        .mean().round(2)
        .sort_values(ascending=False)
        .head(10)
    )
    price_labels = price_by_centre.index.str.split('(').str[0].str.strip().tolist()
    price_values = price_by_centre.values.tolist()

    # ── Donut: food cuisine breakdown only ─────────────────────────
    cuisine_counts_s = food_stalls['cuisine_type'].value_counts().head(8)
    cuisine_labels   = cuisine_counts_s.index.tolist()
    cuisine_counts   = cuisine_counts_s.values.tolist()

    # ── Line: quarterly closure counts ────────────────────────────
    quarter_labels = ['Q1 2026', 'Q2 2026', 'Q3 2026', 'Q4 2025']
    quarter_cols   = ['q1_cleaningstartdate', 'q2_cleaningstartdate',
                      'q3_cleaningstartdate', 'q4_cleaningstartdate']
    closure_counts = []
    for col in quarter_cols:
        valid = cl[col].notna() & (~cl[col].str.upper().isin(['TBC', 'NIL', 'NA']))
        closure_counts.append(int(valid.sum()))

    # ── Horizontal bar: top 8 stalls by avg review rating ──────────
    stall_avg = (
        rev.groupby('stall_id')['rating']
        .mean().round(2)
        .reset_index()
        .rename(columns={'rating': 'avg_rating'})
    )
    top8 = (
        stall_avg.merge(food_stalls[['stall_id', 'stall_name']], on='stall_id')
        .nlargest(8, 'avg_rating')[['stall_name', 'avg_rating']]
    )
    stall_names  = top8['stall_name'].tolist()
    stall_scores = top8['avg_rating'].tolist()

# ── Hawker Centre Explorer dropdown list ──────────────────────
    all_centres = (
             hc[['center_id', 'center_name']]
             .sort_values('center_name')
             .to_dict(orient='records')
          )

    return render_template(
        "dashboard.html",
        username       = session["username"],
        active_page    = "dashboard",
        total_stalls   = f"{total_stalls:,}",
        total_centres  = total_centres,
        avg_rating     = avg_rating,
        total_reviews  = f"{total_reviews:,}",
        avg_price      = avg_price,
        price_labels   = price_labels,
        price_values   = price_values,
        cuisine_labels = cuisine_labels,
        cuisine_counts = cuisine_counts,
        trend_months   = quarter_labels,
        trend_scores   = closure_counts,
        top_stall_names  = stall_names,
        top_stall_scores = stall_scores,
        all_centres=all_centres,
    )


@app.route("/api/hawker_centre_stats")
def hawker_centre_stats():
    """
    Returns JSON with all stats for a single hawker centre.
    Query param: ?center_id=<int>
    """
    center_id = request.args.get("center_id", type=int)
    if center_id is None:
        return jsonify({"error": "center_id required"}), 400

    # ── Load data ────────────────────────────────────────────────────
    hc = pd.read_csv(CENTRES_CSV)
    cl = pd.read_csv(CLOSURES_CSV)
    menu = pd.read_csv(MENU_CSV)
    rev = pd.read_csv(REVIEWS_CSV)
    stalls = pd.read_csv(STALLS_CSV)

    MARKET_TYPES = {
        'Dry Goods', 'Hardware', 'Fruits', 'Seafood',
        'Sundries', 'Poultry', 'Vegetables', 'Wet Market'
    }

    # ── Validate centre ──────────────────────────────────────────────
    centre_row = hc[hc['center_id'] == center_id]
    if centre_row.empty:
        return jsonify({"error": "centre not found"}), 404
    centre_info = centre_row.iloc[0]

    # ── Stalls in this centre (food stalls only) ─────────────────────
    hc_stalls = stalls[
        (stalls['hawker_center_id'] == center_id) &
        (~stalls['cuisine_type'].isin(MARKET_TYPES))
        ]

    total_stalls = len(hc_stalls)

    # ── Average rating ────────────────────────────────────────────────
    stall_ids = hc_stalls['stall_id'].tolist()
    hc_reviews = rev[rev['stall_id'].isin(stall_ids)]
    avg_rating = (
        round(float(hc_reviews['rating'].mean()), 2)
        if not hc_reviews.empty else None
    )

    # ── Average price ─────────────────────────────────────────────────
    hc_menu = menu[menu['stall_id'].isin(stall_ids)]
    avg_price = (
        round(float(hc_menu['price'].mean()), 2)
        if not hc_menu.empty else None
    )

    # ── Area / region ─────────────────────────────────────────────────
    # Try common column names; adapt if your CSV uses a different one.
    area = None
    for col in ['area', 'region', 'location_area', 'town', 'zone']:
        if col in centre_info.index and pd.notna(centre_info[col]):
            area = str(centre_info[col])
            break
    if area is None:
        area = "Central"  # sensible fallback

    # ── Cuisine breakdown ─────────────────────────────────────────────
    cuisine_series = (
        hc_stalls['cuisine_type']
            .value_counts()
            .head(10)
    )
    cuisine_labels = cuisine_series.index.tolist()
    cuisine_counts = [int(v) for v in cuisine_series.values]

    # ── Closure dates for this centre ─────────────────────────────────
    # The closures CSV matches on centre name; adapt key if needed.
    closures_dict = {"q1": [], "q2": [], "q3": [], "q4": []}

    # Try matching by center_id first, then by name
    cl_row = cl[cl.get('center_id', pd.Series(dtype=int)) == center_id] if 'center_id' in cl.columns else pd.DataFrame()
    if cl_row.empty:
        # Fuzzy-ish name match (strip anything in parentheses)
        cname = str(centre_info.get('center_name', '')).split('(')[0].strip().lower()
        cl['_name_clean'] = cl.iloc[:, 0].astype(str).str.split('(').str[0].str.strip().str.lower()
        cl_row = cl[cl['_name_clean'] == cname]

    if not cl_row.empty:
        row = cl_row.iloc[0]
        quarter_cols = {
            'q1': 'q1_cleaningstartdate',
            'q2': 'q2_cleaningstartdate',
            'q3': 'q3_cleaningstartdate',
            'q4': 'q4_cleaningstartdate',
        }
        for qkey, col in quarter_cols.items():
            if col in row.index:
                val = str(row[col]).strip()
                if val and val.upper() not in ('TBC', 'NIL', 'NA', 'NAN', ''):
                    # May be comma-separated date ranges
                    dates = [d.strip() for d in val.split(',') if d.strip()]
                    closures_dict[qkey] = dates

    # ── Top-rated stalls (up to 8) ────────────────────────────────────
    if not hc_reviews.empty:
        stall_avg = (
            hc_reviews.groupby('stall_id')['rating']
                .mean().round(2)
                .reset_index()
                .rename(columns={'rating': 'avg_rating'})
        )
        top8 = (
            stall_avg
                .merge(hc_stalls[['stall_id', 'stall_name']], on='stall_id')
                .nlargest(8, 'avg_rating')[['stall_name', 'avg_rating']]
        )
        top_stalls = [
            {"name": str(r['stall_name']), "rating": round(float(r['avg_rating']), 2)}
            for _, r in top8.iterrows()
        ]
    else:
        top_stalls = []

    # ── Price range distribution (for the bar chart) ──────────────────
    if not hc_menu.empty:
        bins = [0, 3, 5, 8, 10, 15, float('inf')]
        labels = ['<$3', '$3–5', '$5–8', '$8–10', '$10–15', '>$15']
        hc_menu = hc_menu.copy()
        hc_menu['price_band'] = pd.cut(
            hc_menu['price'], bins=bins, labels=labels, right=True
        )
        band_counts = hc_menu['price_band'].value_counts().reindex(labels, fill_value=0)
        price_range_labels = labels
        price_range_counts = [int(v) for v in band_counts.values]
    else:
        price_range_labels = []
        price_range_counts = []

    return jsonify({
        "center_id": center_id,
        "center_name": str(centre_info.get('center_name', '')),
        "area": area,
        "total_stalls": total_stalls,
        "avg_rating": avg_rating,
        "avg_price": avg_price,
        "cuisine_labels": cuisine_labels,
        "cuisine_counts": cuisine_counts,
        "closures": closures_dict,
        "top_stalls": top_stalls,
        "price_range_labels": price_range_labels,
        "price_range_counts": price_range_counts,
    })

# ── Cuisines (ACTIVE) ─────────────────────────────────────────────────────────
@app.route('/cuisines')
@login_required
def cuisines():
    selected_cuisine = request.args.get('cuisine', None)
    selected_stars = request.args.get('stars', None)
    selected_sort = request.args.get('sort', 'score')
    search_query = request.args.get('q', '').strip().lower()
    selected_allergens = request.args.getlist('allergens')  # e.g. ['gluten', 'dairy']
    max_price = request.args.get('max_price', 15, type=float)  # slider: $1–$15, default = show all

    handler = CuisineFeatureHandler()
    profile = da.get_profile(session["username"])

    stalls_df = handler._stall_base()
    stalls_df = stalls_df.merge(handler._get_review_scores(), on='stall_id', how='left')
    stalls_df['n_reviews'] = stalls_df['n_reviews'].fillna(0).astype(int)
    stalls_df['avg_rating'] = stalls_df['avg_rating'].fillna(0.0)
    stalls_df['bayes_score'] = stalls_df['bayes_score'].fillna(0.0)

    coords = None
    if profile and profile.location_lat is not None and profile.location_lng is not None:
        coords = (float(profile.location_lat), float(profile.location_lng))

    if coords and {"latitude_hc", "longitude_hc"}.issubset(stalls_df.columns):
        stalls_df["distance_km"] = stalls_df.apply(
            lambda r: haversine_km(coords[0], coords[1], float(r["latitude_hc"]), float(r["longitude_hc"]))
            if pd.notna(r["latitude_hc"]) and pd.notna(r["longitude_hc"]) else None,
            axis=1,
        )
    else:
        stalls_df["distance_km"] = None

    cuisines_list = handler.get_available_cuisines()
    onboarding_cuisines = [c.lower() for c in (profile.preferred_cuisines if profile else [])]
    default_allergens = [a.lower() for a in (profile.allergens if profile else [])]
    if not selected_allergens and default_allergens and "allergens" not in request.args:
        selected_allergens = default_allergens

    # Build the default stall pool, hoisting onboarding-preferred cuisines to the top
    # when no explicit cuisine filter has been selected by the user.
    if not selected_cuisine and onboarding_cuisines:
        preferred_mask = stalls_df['cuisine_type'].str.lower().isin(onboarding_cuisines)
        other_df = (
            stalls_df[~preferred_mask]
            .sort_values('bayes_score', ascending=False)
        )

        # Build a per-cuisine list sorted by score, then round-robin interleave
        # so all chosen cuisines appear evenly rather than one dominating.
        cuisine_buckets = [
            stalls_df[stalls_df['cuisine_type'].str.lower() == c]
            .sort_values('bayes_score', ascending=False)
            .to_dict(orient='records')
            for c in onboarding_cuisines
        ]
        interleaved = []
        i = 0
        while len(interleaved) < 50 and any(cuisine_buckets):
            bucket = cuisine_buckets[i % len(cuisine_buckets)]
            if bucket:
                interleaved.append(bucket.pop(0))
            i += 1

        slots_left = max(0, 50 - len(interleaved))
        filler_records = other_df.head(slots_left).to_dict(orient='records')
        varied = pd.DataFrame(interleaved + filler_records)
    else:
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

    # Filter by cuisine
    if selected_cuisine:
        stalls_list = [
            s for s in stalls_list
            if selected_cuisine in s.get('cuisine_type', '').lower()
        ]

    # Filter by stars
    if selected_stars:
        min_stars = float(selected_stars)
        stalls_list = [
            s for s in stalls_list
            if s.get('avg_rating', 0) >= min_stars
        ]

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

    # Filter by max price
    if max_price is not None:
        menu_df = handler.merged_df

        # Build stall_id -> min_price map
        menu_df = handler.merged_df.copy()
        menu_df['price'] = pd.to_numeric(menu_df['price'], errors='coerce')

        min_price_map = (
            menu_df.groupby('stall_id')['price']
            .min()
            .to_dict()
        )

        stalls_list = [
            s for s in stalls_list
            if min_price_map.get(s['stall_id'], float('inf')) <= max_price
        ]
    # Sort — when onboarding cuisines drive the default view and no explicit
    # sort is requested, preserve the round-robin interleaved order as-is.
    using_onboarding_order = (not selected_cuisine and bool(onboarding_cuisines)
                              and selected_sort == 'score')
    if selected_sort == 'rating':
        stalls_list.sort(key=lambda x: x.get('avg_rating', 0), reverse=True)
    elif selected_sort == 'reviews':
        stalls_list.sort(key=lambda x: x.get('n_reviews', 0), reverse=True)
    elif selected_sort == 'distance':
        stalls_list.sort(key=lambda x: x.get('distance_km', 999))
    elif not using_onboarding_order:
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
                           onboarding_cuisines=onboarding_cuisines,
                           )

# ------ PRICING -------
@app.route("/pricing")
@login_required
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
        'from_page': request.args.get('from', ''),
        'back_stall_id': request.args.get('back_stall_id', ''),
    }

    # Top 3 reviews for this stall (shown at bottom of pricing page)
    from features_reviews import ReviewFeature
    rf = ReviewFeature()
    review_sort = request.args.get('review_sort', 'helpful')  # helpful | recent | stars

    rev_df = rf.get_reviews_for_stall(stall_id, limit=100)
    all_top = rf.get_display_rows(rev_df)

    if review_sort == 'recent':
        all_top = sorted(all_top, key=lambda r: r['date'], reverse=True)
    elif review_sort == 'stars':
        all_top = sorted(all_top, key=lambda r: r['rating'], reverse=True)
    else:  # helpful (default)
        all_top = sorted(all_top, key=lambda r: r['helpful_count'], reverse=True)

    top_reviews = all_top[:3]

    return render_template("feature_pricing.html",
                           stall=stall,
                           menu_items=menu_items,
                           error=None,
                           back_params=back_params,
                           top_reviews=top_reviews,
                           review_sort=review_sort)

da = TouristProfileDA()           # one shared instance
planner = LocationPlanner()       # one shared instance

"""
    Renders the Update Location & Dates page.
    Reads the current saved values from the DB (via Flask session username)
    and passes them to the template so the status bar and form fields are
    pre-filled.
    """
@app.route("/location")
@login_required
def location():
    profile = da.get_profile(session["username"])

    # Coordinates — tuple or None
    current_coords = None
    if profile and profile.location_lat is not None and profile.location_lng is not None:
        current_coords = (float(profile.location_lat), float(profile.location_lng))

    # Trip dates stored as dd/mm/yyyy in DB — convert to ISO (yyyy-mm-dd) for
    # the HTML date input's value attribute
    trip_start_iso = _ddmmyyyy_to_iso(profile.trip_start) if profile else None
    trip_end_iso   = _ddmmyyyy_to_iso(profile.trip_end)   if profile else None

    today_iso = datetime.now().strftime("%Y-%m-%d")

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
        today_iso        = today_iso,
    )


@app.route("/location/update-location", methods=["POST"])
@login_required
def update_location():
    """
    Handles the Update Location form submission.
    - Calls OneMap via LocationPlanner.get_coords() to resolve address → coords
    - Saves updated coords + radius to the DB
    - Redirects back to /location
    """
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

    flash(f"Location set to: {address} ({coords[0]:.5f}, {coords[1]:.5f}).", "success")
    return redirect(url_for("location"))


@app.route("/location/update-dates", methods=["POST"])
@login_required
def update_trip_dates():
    """
    Handles the Update Trip Dates form submission.
    - HTML date inputs give yyyy-mm-dd; we convert to dd/mm/yyyy to match the
      format used everywhere else in the project (hawker_filter, main.py, etc.)
    - Saves updated dates to the DB without touching coords/radius
    """
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

    # if the user was sent here from the itinerary save flow,
    # send them back to the itinerary now that dates are set.
    redirect_target = session.pop("after_dates_redirect", None)
    return redirect(redirect_target or url_for("location"))


# ── Itinerary  ─────
# These routes expect:
#   da.get_saved_stalls(username)  → list of stall_ids
#   da.add_saved_stall(username, stall_id)
#   da.remove_saved_stall(username, stall_id)
#   da.clear_saved_stalls(username)
#   handler.get_stalls_by_ids(stall_ids, ...) → DataFrame

@app.route("/itinerary/save/<int:stall_id>")
@login_required
def itinerary_save(stall_id):
    da.add_saved_stall(session["username"], stall_id)
    flash("Stall saved to your itinerary.", "success")
    return redirect(url_for("itinerary"))


@app.route("/itinerary/assign/<int:stall_id>/<int:day_index>")
@login_required
def itinerary_assign(stall_id, day_index):
    day_map = da.get_stall_day_map(session["username"])
    day_map[str(stall_id)] = day_index
    da.update_stall_day_map(session["username"], day_map)
    return redirect(url_for("itinerary"))


@app.route("/itinerary")
@login_required
def itinerary():
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
            radius_km=999.0,  # no radius filter — itinerary shows ALL saved stalls
            trip_start=trip_start,
            trip_end=trip_end,
        )
        # avg_rating and n_reviews are already included by get_stalls_by_ids
        # via _aggregate_stalls → _get_review_scores — no extra merge needed
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
            if 'distance_km' not in d:
                d['distance_km'] = None
            itinerary_list.append(d)

    # Build day-by-day structure if trip dates are set
    days = []
    days_count = 0
    unscheduled = []
    trip_start = profile.trip_start if profile else None
    trip_end = profile.trip_end if profile else None

    # stall_day_map: {str(stall_id): day_index} — user-chosen assignments in session
    stall_day_map = da.get_stall_day_map(session["username"])

    if trip_start and trip_end and itinerary_list:
        try:
            start_dt = datetime.strptime(trip_start, "%d/%m/%Y")
            end_dt = datetime.strptime(trip_end, "%d/%m/%Y")
            days_count = (end_dt - start_dt).days + 1

            WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

            # Build empty day buckets
            day_list = []
            for d_idx in range(days_count):
                cur_dt = start_dt + timedelta(days=d_idx)
                day_list.append({
                    "day_num": d_idx + 1,
                    "weekday": WEEKDAYS[cur_dt.weekday()],
                    "date_str": cur_dt.strftime("%d %b %Y"),
                    "stalls": [],
                })

            # Assign stalls: user-chosen day or unscheduled
            for stall in itinerary_list:
                sid_key = str(stall['stall_id'])
                if sid_key in stall_day_map:
                    chosen = stall_day_map[sid_key]
                    if 0 <= chosen < days_count:
                        day_list[chosen]["stalls"].append(stall)
                    else:
                        unscheduled.append(stall)
                else:
                    unscheduled.append(stall)

            days = day_list

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
        unscheduled=unscheduled,
        trip_start=trip_start,
        trip_end=trip_end,
        cuisines_count=len(cuisine_counts),
        cuisine_breakdown=cuisine_breakdown,
        avg_rating=avg_rating,
        route_orders=da.get_route_orders(session["username"]),
        has_location=bool(profile and profile.location_lat is not None and profile.location_lng is not None),
    )


@app.route("/itinerary/optimise/<int:day_index>")
@login_required
def itinerary_optimise(day_index):
    profile = da.get_profile(session["username"])

    coords = None
    if profile and profile.location_lat and profile.location_lng:
        coords = (float(profile.location_lat), float(profile.location_lng))
    if not coords:
        flash("Please set your location before optimising a route.", "error")
        return redirect(url_for("itinerary"))

    saved_ids = da.get_saved_stalls(session["username"])
    handler = CuisineFeatureHandler()
    trip_start = profile.trip_start if profile else None
    trip_end = profile.trip_end if profile else None

    stalls_df = handler.get_stalls_by_ids(
        saved_ids, coords=coords, radius_km=999.0,
        trip_start=trip_start, trip_end=trip_end,
    )
    if stalls_df.empty:
        flash("No stall data found.", "error")
        return redirect(url_for("itinerary"))

    # Find stalls assigned to this day
    stall_day_map = da.get_stall_day_map(session["username"])
    day_stall_ids = [int(sid) for sid, didx in stall_day_map.items() if didx == day_index]
    if not day_stall_ids:
        flash("No stalls assigned to that day yet.", "error")
        return redirect(url_for("itinerary"))

    day_df = stalls_df[stalls_df["stall_id"].isin(day_stall_ids)].copy()
    if day_df.empty or not {"latitude_hc", "longitude_hc"}.issubset(day_df.columns):
        flash("Missing location data for route optimisation.", "error")
        return redirect(url_for("itinerary"))

    route, total_km, total_mins = planner.build_stall_itinerary(
        start_coords=coords,
        stalls_df=day_df,
        max_stops=len(day_stall_ids),
    )
    if not route:
        flash("Could not build a route for that day.", "error")
        return redirect(url_for("itinerary"))

    # Store optimised order + leg info in session keyed by day_index
    route_orders = da.get_route_orders(session["username"])
    route_orders[str(day_index)] = [
        {
            "stall_id": int(stop["stall_id"]),
            "leg_dist_km": round(float(stop["leg_dist_km"]), 2),
            "leg_time_mins": round(float(stop["leg_time_mins"])),
        }
        for stop in route
    ]
    da.update_route_orders(session["username"], route_orders)
    flash(f"Route optimised — {total_km:.1f} km total walk (~{round(total_mins)} mins).", "success")
    return redirect(url_for("itinerary"))


@app.route("/itinerary/reorder/<int:day_index>/<int:stall_id>/<direction>")
@login_required
def itinerary_reorder(day_index, stall_id, direction):
    """Move a stall up or down within the day, then recalculate leg distances
    using the same OneMap walking route API as the optimiser."""
    route_orders = da.get_route_orders(session["username"])
    key = str(day_index)
    order = route_orders.get(key, [])
    ids = [s["stall_id"] for s in order]
    if stall_id not in ids:
        return redirect(url_for("itinerary"))
    idx = ids.index(stall_id)
    if direction == "up" and idx > 0:
        order[idx], order[idx - 1] = order[idx - 1], order[idx]
    elif direction == "down" and idx < len(order) - 1:
        order[idx], order[idx + 1] = order[idx + 1], order[idx]

    # Recalculate leg distances using the same OneMap routing as the optimiser
    handler = CuisineFeatureHandler()
    all_ids = [s["stall_id"] for s in order]
    stalls_df = handler.get_stalls_by_ids(all_ids, coords=None, radius_km=999)
    coord_map = {}
    if not stalls_df.empty:
        for _, row in stalls_df.iterrows():
            sid = int(row["stall_id"])
            lat = row.get("latitude_hc")
            lng = row.get("longitude_hc")
            if lat and lng:
                coord_map[sid] = (float(lat), float(lng))

    order[0]["leg_dist_km"] = None
    order[0]["leg_time_mins"] = None
    for i in range(1, len(order)):
        prev_id = order[i - 1]["stall_id"]
        curr_id = order[i]["stall_id"]
        if prev_id in coord_map and curr_id in coord_map:
            dist_km, time_mins = planner._route_walk_km_mins(
                coord_map[prev_id], coord_map[curr_id]
            )
            order[i]["leg_dist_km"] = round(dist_km, 2)
            order[i]["leg_time_mins"] = round(time_mins)
        else:
            order[i]["leg_dist_km"] = None
            order[i]["leg_time_mins"] = None

    route_orders[key] = order
    da.update_route_orders(session["username"], route_orders)
    return redirect(url_for("itinerary"))


@app.route("/itinerary/route-clear/<int:day_index>")
@login_required
def itinerary_route_clear(day_index):
    """Reset the optimised route for a day back to default order."""
    route_orders = da.get_route_orders(session["username"])
    route_orders.pop(str(day_index), None)
    da.update_route_orders(session["username"], route_orders)
    return redirect(url_for("itinerary"))

@app.route("/itinerary/remove/<int:stall_id>")
@login_required
def itinerary_remove(stall_id):
    current = da.get_saved_stalls(session["username"])
    kept = [sid for sid in current if sid != stall_id]
    da.clear_saved_stalls(session["username"])
    for sid in kept:
        da.add_saved_stall(session["username"], sid)
    # Also clear the day assignment for this stall from the session
    day_map = da.get_stall_day_map(session["username"])
    day_map.pop(str(stall_id), None)
    da.update_stall_day_map(session["username"], day_map)
    flash("Stall removed from your itinerary.", "success")
    return redirect(url_for("itinerary"))

@app.route("/itinerary/clear")
@login_required
def itinerary_clear():
    da.clear_saved_stalls(session["username"])
    flash("Itinerary cleared.", "success")
    return redirect(url_for("itinerary"))

@app.route("/itinerary/export")
@login_required
def itinerary_export():
    """Simple plain-text export of saved stalls."""
    profile = da.get_profile(session["username"])
    saved_ids = da.get_saved_stalls(session["username"])
    handler = CuisineFeatureHandler()
    stall_day_map = da.get_stall_day_map(session["username"])
    route_orders = da.get_route_orders(session["username"])

    lines = ["HAWKER HUNT — MY ITINERARY", "=" * 40]
    if profile and profile.trip_start:
        lines.append(f"Trip: {profile.trip_start} → {profile.trip_end}")
    lines.append("")

    if saved_ids:
        stalls_df = handler.get_stalls_by_ids(saved_ids, coords=None, radius_km=50)
        scores_df = handler._get_review_scores()
        if not stalls_df.empty and not scores_df.empty:
            stalls_df = stalls_df.merge(scores_df, on='stall_id', how='left')
        stall_lookup = {}
        for _, row in stalls_df.iterrows():
            stall_lookup[int(row["stall_id"])] = row

        if profile and profile.trip_start and profile.trip_end:
            start_dt = datetime.strptime(profile.trip_start, "%d/%m/%Y")
            end_dt = datetime.strptime(profile.trip_end, "%d/%m/%Y")
            for day_index in range((end_dt - start_dt).days + 1):
                current_dt = start_dt + timedelta(days=day_index)
                lines.append(f"DAY {day_index + 1} — {current_dt.strftime('%A %d %b %Y')}")

                ordered_ids = [int(s["stall_id"]) for s in route_orders.get(str(day_index), [])]
                assigned_ids = [
                    int(stall_id) for stall_id, assigned_day in stall_day_map.items()
                    if assigned_day == day_index and int(stall_id) in stall_lookup
                ]
                for sid in assigned_ids:
                    if sid not in ordered_ids:
                        ordered_ids.append(sid)

                if not ordered_ids:
                    lines.append("  No stalls scheduled.")
                else:
                    for sid in ordered_ids:
                        row = stall_lookup.get(sid)
                        if row is None:
                            continue
                        lines.append(f"  • {row.get('stall_name', '?')} @ {row.get('hawker_name', '?')}")
                        lines.append(f"    Cuisine: {row.get('cuisine_type', '?')}")
                        if pd.notna(row.get('address_myenv')):
                            lines.append(f"    Address: {row.get('address_myenv')}")
                        if pd.notna(row.get('avg_rating')):
                            lines.append(f"    Rating: {float(row.get('avg_rating')):.1f}")
                        if pd.notna(row.get('google_3d_view')):
                            lines.append(f"    Maps: {row.get('google_3d_view')}")
                lines.append("")

        unscheduled_ids = [
            int(stall_id) for stall_id in saved_ids
            if str(stall_id) not in stall_day_map and int(stall_id) in stall_lookup
        ]
        if unscheduled_ids:
            lines.append("UNSCHEDULED")
            for sid in unscheduled_ids:
                row = stall_lookup[sid]
                lines.append(f"  • {row.get('stall_name', '?')} @ {row.get('hawker_name', '?')}")
                lines.append(f"    Cuisine: {row.get('cuisine_type', '?')}")
            lines.append("")

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
@login_required
def closure():
    feature = HawkerClosureFeature(project_root=BASE_DIR)
    closures_df = feature.load_hawker_data().head(20)
    records = closures_df.fillna("").to_dict(orient="records")
    return render_template('feature_closure.html', active_page='closure', closures=records)

# ── Reviews ───────────────────────────────────────────────────────────────────
review_feature = ReviewFeature()

@app.route("/reviews")
@login_required
def reviews():
    profile = da.get_profile(session["username"])
    active_tab = request.args.get("tab", "read")
    stall_id = request.args.get("stall_id", None, type=int)
    selected_stars = request.args.get("stars", "").strip()
    write_stall_id = request.args.get("write_stall_id", "")
    write_stall_name = request.args.get("write_stall_name", "")

    # ── Load reviews for the selected stall ───────────────────────
    reviews_list = []
    selected_stall_name = ""
    selected_stall_hawker = ""
    avg_rating = None
    total_review_count = 0

    if stall_id:
        # Get stall name + hawker centre name
        from feature_cuisines import CuisineFeatureHandler
        handler = CuisineFeatureHandler()
        stall_row = handler._stall_base()
        stall_row = stall_row[stall_row["stall_id"] == stall_id]
        if not stall_row.empty:
            selected_stall_name = str(stall_row.iloc[0].get("stall_name", ""))
            selected_stall_hawker = str(stall_row.iloc[0].get("hawker_name", ""))

        # Get ALL reviews for this stall (no limit)
        rev_df = review_feature.get_reviews_for_stall(stall_id, limit=200)
        all_rows = review_feature.get_display_rows(rev_df)
        total_review_count = len(all_rows)

        # Average rating across all reviews
        if all_rows:
            avg_rating = sum(r["rating"] for r in all_rows) / len(all_rows)

        # Apply star filter
        if selected_stars:
            try:
                star_val = int(selected_stars)
                all_rows = [r for r in all_rows if round(r["rating"]) == star_val]
            except ValueError:
                pass

        # Apply sort
        review_sort = request.args.get('review_sort', 'helpful')
        if review_sort == 'date':
            all_rows = sorted(all_rows, key=lambda r: r['date'], reverse=True)
        elif review_sort == 'stars':
            all_rows = sorted(all_rows, key=lambda r: r['rating'], reverse=True)
        elif review_sort == 'verified':
            all_rows = sorted(all_rows, key=lambda r: (r['verified_purchase'] == 'Yes'), reverse=True)
        else:  # helpful (default)
            all_rows = sorted(all_rows, key=lambda r: r['helpful_count'], reverse=True)

        reviews_list = all_rows

        # Pre-fill write tab with this stall
        if not write_stall_id:
            write_stall_id = str(stall_id)
            write_stall_name = selected_stall_name

    # ── My Reviews (reviews written by current user) ──────────────
    username = session.get("username", "")
    my_rev_df = review_feature.get_reviews_by_user(username)
    my_reviews = review_feature.get_display_rows(my_rev_df)

    return render_template(
        "feature_reviews.html",
        active_tab=active_tab,
        # sidebar
        trip_start=profile.trip_start if profile else None,
        trip_end=profile.trip_end if profile else None,
        saved_stall_count=len(da.get_saved_stalls(session["username"])),
        # my reviews tab
        my_reviews = my_reviews,
        # read tab
        selected_stall_id=stall_id,
        selected_stall_name=selected_stall_name,
        selected_stall_hawker=selected_stall_hawker,
        selected_stars=selected_stars,
        reviews_list=reviews_list,
        avg_rating=avg_rating,
        total_review_count=total_review_count,
        back_stall_id=stall_id,
        review_sort = request.args.get('review_sort', 'helpful'),
        # write tab
        write_stall_id=write_stall_id,
        write_stall_name=write_stall_name,
        username=session.get("username", ""),
    )

@app.route("/reviews/submit", methods=["POST"])
@login_required
def reviews_submit():

    stall_id = request.form.get("stall_id", type=int)
    rating_raw = request.form.get("rating", "").strip()
    review_text = request.form.get("review_text", "").strip()
    user_name = request.form.get("user_name", "Anonymous").strip() or "Anonymous"
    back_stall_id = request.form.get("back_stall_id", "").strip()

    if not stall_id:
        flash("Please select a stall before submitting.", "error")
        return redirect(url_for("reviews"))

    try:
        rating = float(rating_raw)
        if not 0 <= rating <= 5:
            raise ValueError
    except (ValueError, TypeError):
        flash("Please select a rating between 0 and 5.", "error")
        return redirect(url_for("reviews") + f"?stall_id={back_stall_id}&tab=write" if back_stall_id else url_for("reviews"))

    if not review_text:
        flash("Review text cannot be empty.", "error")
        return redirect(url_for("reviews") + f"?stall_id={back_stall_id}&tab=write" if back_stall_id else url_for("reviews"))

    try:
        review_feature.add_review(
            stall_id=stall_id,
            rating=rating,
            review_text=review_text,
            user_name=user_name,
        )
        flash("Your review has been submitted. Thank you!", "success")
    except Exception as e:
        flash(f"Could not save review: {e}", "error")

    redirect_url = f"/reviews?stall_id={stall_id}&tab=read" if stall_id else url_for("reviews")

    return redirect(redirect_url)

@app.route("/reviews/helpful", methods = ["POST"])
def reviews_helpful():
    review_id = request.form.get("review_id", type=int)
    stall_id = request.form.get("stall_id", type=int)
    stars = request.form.get("stars", "")

    if review_id:
        voted = session.get("helpful_votes", [])
        if review_id in voted:
            flash("You already marked this review as helpful.", "info")
        else:
            try:
                review_feature.mark_review_helpful(review_id)
                voted.append(review_id)
                session["helpful_votes"] = voted
                flash("Marked as helpful!", "success")
            except Exception as e:
                flash(f"Could not update: {e}", "error")

    redirect_url = f"/reviews?stall_id={stall_id}&tab=read"
    if stars:
        redirect_url += f"&stars={stars}"
    return redirect(redirect_url)

@app.route("/reviews/search")
def reviews_search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    try:
        matches = review_feature.search_stalls(q, limit=8)
        results = []
        for _, row in matches.iterrows():
            results.append({
                "stall_id":   int(row["stall_id"]),
                "stall_name": str(row["stall_name"]),
                "hawker_name": "",
            })
        return jsonify(results)
    except Exception:
        return jsonify([])

@app.route("/onboarding", methods=["GET", "POST"])
def onboarding():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        name = request.form.get("name", "").strip()
        allergens = request.form.getlist("allergens")
        preferred_cuisines = request.form.getlist("preferred_cuisines")
        location_lat = float(request.form.get("location_lat", 1.3521))
        location_lng = float(request.form.get("location_lng", 103.8198))
        radius_km = float(request.form.get("radius_km", 3))
        trip_start_raw = request.form.get("trip_start", "").strip()
        trip_end_raw = request.form.get("trip_end", "").strip()

        if not username or not password or not name:
            flash("Please fill in your name, username, and password.", "error")
            return redirect(url_for("onboarding"))

        trip_start = _iso_to_ddmmyyyy(trip_start_raw) if trip_start_raw else None
        trip_end = _iso_to_ddmmyyyy(trip_end_raw) if trip_end_raw else None

        if trip_start and trip_end:
            start_dt = datetime.strptime(trip_start, "%d/%m/%Y")
            end_dt = datetime.strptime(trip_end, "%d/%m/%Y")
            if start_dt > end_dt:
                flash("Trip start must be before trip end.", "error")
                return redirect(url_for("onboarding"))

        profile = TouristProfile(
            username=username,
            password=password,
            name=name,
            allergens=allergens,
            preferred_cuisines=preferred_cuisines,
            created_at=datetime.now().isoformat(),
            saved_stalls=[],
            saved_hawker_center_ids=[],
            location_lat=location_lat,
            location_lng=location_lng,
            radius_km=radius_km,
            trip_start=trip_start,
            trip_end=trip_end,
            stall_day_map={},
            route_orders={},
        )

        try:
            da.insert_profile(profile)
        except sqlite3.IntegrityError:
            flash("That username already exists. Please choose another one.", "error")
            return redirect(url_for("onboarding"))

        session["username"] = username
        session["preferred_cuisines"] = preferred_cuisines
        flash("Account created successfully!", "success")
        return redirect(url_for("dashboard"))

    return render_template(
        "feature_onboarding_edit.html",
        active_page="onboarding",
        allergens=[
            "Nuts", "Shellfish", "Dairy", "Gluten",
            "Eggs", "Soy", "Fish", "Sesame"
        ],
        cuisines=[
            "Chinese", "Malay", "Indian", "Japanese", "Korean", "Thai",
            "Western", "Seafood", "Vegetables", "Beverage",
            "Dessert", "Fruits", "Peranakan"
        ],
        singapore_center={"lat": 1.3521, "lng": 103.8198},
        selected_cuisines=[],
        selected_allergens=[],
        prefill_name="",
        prefill_username="",
        current_trip_start=None,
        current_trip_end=None,
        current_radius=3,
        hide_account_fields=False,
    )

@app.route("/preferences", methods=["GET", "POST"])
@login_required
def preferences():
    profile = da.get_profile(session["username"])
    if not profile:
        flash("Profile not found.", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        allergens = request.form.getlist("allergens")
        preferred_cuisines = request.form.getlist("preferred_cuisines")
        trip_start_raw = request.form.get("trip_start", "").strip()
        trip_end_raw = request.form.get("trip_end", "").strip()
        radius_km = float(request.form.get("radius_km", profile.radius_km or 3))
        coords = None
        if profile.location_lat is not None and profile.location_lng is not None:
            coords = (float(profile.location_lat), float(profile.location_lng))

        trip_start = _iso_to_ddmmyyyy(trip_start_raw) if trip_start_raw else profile.trip_start
        trip_end = _iso_to_ddmmyyyy(trip_end_raw) if trip_end_raw else profile.trip_end

        if trip_start and trip_end:
            start_dt = datetime.strptime(trip_start, "%d/%m/%Y")
            end_dt = datetime.strptime(trip_end, "%d/%m/%Y")
            if start_dt > end_dt:
                flash("Trip start must be before trip end.", "error")
                return redirect(url_for("preferences"))

        da.update_preferences(session["username"], allergens, preferred_cuisines)
        da.update_trip_context(session["username"], coords, radius_km, trip_start, trip_end)
        flash("Preferences updated.", "success")
        return redirect(url_for("preferences"))

    return render_template(
        "feature_onboarding_edit.html",
        active_page="preferences",
        allergens=[
            "Nuts", "Shellfish", "Dairy", "Gluten",
            "Eggs", "Soy", "Fish", "Sesame"
        ],
        cuisines=[
            "Chinese", "Malay", "Indian", "Japanese", "Korean", "Thai",
            "Western", "Seafood", "Vegetables", "Beverage",
            "Dessert", "Fruits", "Peranakan"
        ],
        singapore_center={
            "lat": profile.location_lat if profile.location_lat is not None else 1.3521,
            "lng": profile.location_lng if profile.location_lng is not None else 103.8198,
        },
        selected_cuisines=profile.preferred_cuisines,
        selected_allergens=profile.allergens,
        prefill_name=profile.name,
        prefill_username=profile.username,
        current_trip_start=_ddmmyyyy_to_iso(profile.trip_start),
        current_trip_end=_ddmmyyyy_to_iso(profile.trip_end),
        current_radius=profile.radius_km,
        hide_account_fields=True,
    )

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
