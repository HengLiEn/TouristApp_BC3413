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
@app.route("/cuisines")
def cuisines():
    handler = CuisineFeatureHandler()
    prefs = CuisinePreferences()
    available_cuisines = handler.get_available_cuisines()
    top_stalls = handler.get_top_nearby_stalls(prefs=prefs, coords=None)
    stalls_list = top_stalls.to_dict(orient="records")
    return render_template("feature_cuisines.html",
                           cuisines=available_cuisines,
                           stalls=stalls_list)

# @app.route("/pricing")
# def pricing():
#     return render_template("pricing.html")

# @app.route("/location")
# def location():
#     return render_template("location.html")

# @app.route("/closure")
# def closure():
#     return render_template("closure.html")

# @app.route("/reviews")
# def reviews():
#     return render_template("reviews.html")

# @app.route("/onboarding")
# def onboarding():
#     return render_template("onboarding.html")

# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True)