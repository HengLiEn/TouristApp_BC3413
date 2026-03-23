from flask import Flask, render_template, request, redirect, url_for, session, flash
from feature_cuisines import CuisineFeatureHandler, CuisinePreferences
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

@app.route("/location")
def location():
    return render_template('feature_onboarding.html', active_page='location')

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