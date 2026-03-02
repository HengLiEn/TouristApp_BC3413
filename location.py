#possible improvements im considering:
#1. live location - abit hard
#2. do i need to export the final itinerary out?
#3. include car / public transportation

#IMPROVED VERSION:
#1. Used OneMap for a more accurante distance measurement other than geodesic.
#2. show travel distance and time

import pandas as pd
from geopy.distance import geodesic
import sys
import os
from datetime import datetime
import requests

#import datasets
try:
    df = pd.read_csv(os.path.join("dataset", "Hawker Centre Data", "DatesofHawkerCentresClosure.csv"))
    try:
        df_stalls = pd.read_csv(os.path.join("dataset", "Multiple Stalls Menu and Data", "stalls.csv"))
        merged_stalls = pd.merge(df_stalls, df, left_on='hawker_center_id', right_on='serial_no', how='inner')
    except FileNotFoundError:
        print("Warning: 'stalls.csv' not found.")
        merged_stalls = pd.DataFrame()
except FileNotFoundError:
    print("Error: Hawker dataset not found.")
    sys.exit()

def get_coords(address):
    "Uses OneMap API to turn SG address/postal code into coordinates"
    try:
        # OneMap Search Endpoint
        url = f"https://www.onemap.gov.sg/api/common/elastic/search?searchVal={address}&returnGeom=Y&getAddrDetails=Y&pageNum=1"
        response = requests.get(url, timeout=5)
        data = response.json()
        # Check if OneMap found any results
        if data.get('found', 0) > 0:
            result = data['results'][0]
            return (float(result['LATITUDE']), float(result['LONGITUDE']))
        else:
            print(f"OneMap could not find: {address}")
            return None
    except Exception as e:
        print(f"Connection error: {e}")
        return None


def calculate_best_route(start_coords, hcs_df):
    "Finds the nearest next stop and tracks total distance/time"
    route = []
    remaining = hcs_df.copy()
    current_loc = start_coords
    total_km = 0
    total_mins = 0

    print("\nCalculating real-world travel distances via OneMap...")

    while not remaining.empty:
        best_dist = float('inf')
        best_time = 0
        nearest_idx = None

        for idx, row in remaining.iterrows():
            url = f"https://www.onemap.gov.sg/api/public/routing/route?start={current_loc[0]},{current_loc[1]}&end={row['latitude_hc']},{row['longitude_hc']}&routeType=walk"
            try:
                response = requests.get(url, timeout=5).json()
                dist_km = response['route_summary']['total_distance'] / 1000
                time_mins = response['route_summary']['total_time'] / 60
            except:
                # Fallback: Approx 12 mins per km for walking
                dist_km = geodesic(current_loc, (row['latitude_hc'], row['longitude_hc'])).km
                time_mins = dist_km * 12

            if dist_km < best_dist:
                best_dist = dist_km
                best_time = time_mins
                nearest_idx = idx

        nearest_row = remaining.loc[nearest_idx].to_dict()
        # Store travel stats from the PREVIOUS stop to THIS stop
        nearest_row['leg_dist'] = best_dist
        nearest_row['leg_time'] = best_time

        total_km += best_dist
        total_mins += best_time

        route.append(nearest_row)
        current_loc = (nearest_row['latitude_hc'], nearest_row['longitude_hc'])
        remaining = remaining.drop(nearest_idx)

    return route, total_km, total_mins

# --- MAIN PROGRAM ---
print("--- Advanced Hawker Centre & Stall Itinerary Planner ---")

# 1. Get User Location (Only happens once at start)
while True:
    user_addr = input("Enter your current location (e.g. 'Bedok' or '639798'): ")
    user_coords = get_coords(user_addr)
    if user_coords:
        print("Location recognized!")
        break
    print("Location not found. Try again.")

all_itineraries = []

# 2. Main Planning Loop (Allows multiple itineraries)
while True:
    # --- Date Validation ---
    while True:
        date_input = input("\nEnter the date (YYYY-MM-DD): ").strip()
        try:
            valid_date = datetime.strptime(date_input, "%Y-%m-%d")
            explore_date = date_input
            break
        except ValueError:
            print("Invalid format! Please use YYYY-MM-DD (e.g., 2026-08-09).")

    selected_rows = []

    # 2. Select up to 5 Hawker Centres
    while len(selected_rows) < 5:
        print(f"\n--- Itinerary for {explore_date} (Stops: {len(selected_rows)}/5) ---")
        print("[1] Search Hawker Centre Name  [2] Search Stall Name  [done] Finish Selection")
        search_mode = input("Option: ").strip().lower()

        if search_mode == 'done':
            if selected_rows:
                break
            else:
                print("Pick at least one!"); continue

        query = input("Enter Search Term: ").strip()
        matches = pd.DataFrame()

        if search_mode == '1':
            matches = df[df['name'].str.contains(query, case=False, na=False)]
        elif search_mode == '2' and not merged_stalls.empty:
            matches = merged_stalls[merged_stalls['stall_name'].str.contains(query, case=False, na=False)]
            if len(matches) > 10:
                print(f"Found {len(matches)} stalls. Filter by location:")
                locs = matches['name'].unique()
                for i, l in enumerate(locs, 1): print(f"{i}. {l}")

                user_selection = input("Enter choice number: ")
                try:
                    sel_idx = int(user_selection) - 1
                    if 0 <= sel_idx < len(locs):
                        matches = matches[matches['name'] == locs[sel_idx]]
                    else:
                        print("Invalid number. Showing all stalls.")
                except ValueError:
                    print("Invalid input. Showing all stalls.")

        if matches.empty:
            print("No results.");
            continue

        #Display results with temporary IDs starting from index 1
        for i, (idx, row) in enumerate(matches.iterrows()):
            name_str = row['name'] if search_mode == '1' else f"{row['stall_name']} ({row['name']})"
            print(f"[{i + 1}] {name_str}")

        choice = input("\nEnter choice number: ")
        if not choice.strip(): continue

        try:
            indices = [int(x.strip()) - 1 for x in choice.split(',')]
            for i in indices:
                if 0 <= i < len(matches):
                    selected_rows.append(matches.iloc[i].to_dict())
                    print(f"Added: {matches.iloc[i]['name']}")
        except:
            print("Invalid selection.")

    # 3. Calculate Initial Best Route
    selected_df = pd.DataFrame(selected_rows)
    if not selected_df.empty:
        selected_df = selected_df.drop_duplicates(subset=['serial_no'])
    itinerary, total_dist, total_time = calculate_best_route(user_coords, selected_df)

    # 4. Edit Loop
    while True:
        print("\n--- CURRENT ITINERARY ---")
        for i, hc in enumerate(itinerary, 1): print(f"{i}. {hc['name']}")

        action = input("\n[1] Finalize  [2] Reorder  [3] Remove a stop: ")

        if action == '1':
            break
        elif action == '2':
            order = input("Enter order (e.g. 2,1): ")
            try:
                itinerary = [itinerary[int(x) - 1] for x in order.split(',')]
            except:
                print("Error reordering.")
        elif action == '3':
            try:
                itinerary.pop(int(input("Enter the stop number to remove: ")) - 1)
            except:
                print("Error removing.")

        if not itinerary: break

# 5. Final Display
    if itinerary:
        print("\n" + "═" * 50)
        print(f"SAVED ITINERARY FOR: {explore_date}")
        print("═" * 50)

        for i, hc in enumerate(itinerary, 1):
            travel_info = "STARTING POINT" if i == 1 else f"🚶 Travel: {hc['leg_dist']:.2f} km (~{round(hc['leg_time'])} mins)"

            print(f"\n📍 STOP {i}: {hc['name']}")
            print(f"   {travel_info}")
            print(f"   🏠 Address: {hc['address_myenv']}")
            print(f"   🔗 Maps: {hc['google_3d_view']}")
            print(f"   📸 Photo: {hc['photourl']}")
            print("-" * 30)

        print(f"\nDAILY SUMMARY:")
        print(f"   Total Distance: {total_dist:.2f} km")
        print(f"   Total Travel Time: {round(total_time)} mins")
        print("═" * 50)

        # Store for history
        all_itineraries.append({
            'date': explore_date,
            'route': itinerary,
            'total_dist': total_dist,
            'total_time': total_time
        })

    # 6. Exit Strategy & Detailed Master History
    cont = input("\nPlan another itinerary for a different date? (yes/no): ").lower()
    if cont != 'yes':
        print("═" * 19 + "YOUR MASTER HAWKER PLAN" + "═" * 19)

        if not all_itineraries:
            print("No itineraries saved. Happy eating!")
        else:
            # Sort chronologically by date
            all_itineraries.sort(key=lambda x: x['date'])

            for session in all_itineraries:
                print(f"\nDATE: {session['date']}")
                print(f"TOTALS: {session['total_dist']:.2f}km | ~{round(session['total_time'])} mins travel")
                print("─" * 40)

                for i, stop in enumerate(session['route'], 1):
                    # Using 'stop' instead of 'hc' ensures the correct data is shown for each entry
                    dist_info = "START" if i == 1 else f"🚶 {stop['leg_dist']:.2f}km (~{round(stop['leg_time'])}m)"

                    print(f"📍 STOP {i}: {stop['name']}")
                    print(f"   {dist_info}")
                    print(f"   🏠 Address: {stop['address_myenv']}")
                    print(f"   🔗 Maps: {stop['google_3d_view']}")
                    print(f"   📸 Photo: {stop['photourl']}")
                    print("   " + "┈" * 20)

                print("═" * 45)

        print("\nAll plans finalized. Have a great time exploring Singapore's delicacy!")
        break
