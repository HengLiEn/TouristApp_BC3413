#possible improvements im considering:
#1. live location
#2. allow location name and number when chosing for stalls
#3. show travel distance and time
#4. find a more accurante distance measurement other than geodesic
#5. if date chosen is before current date, ask for another date
# - if wrong format, ask for correct format.

import pandas as pd
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
import sys
import os

# Load the datasets
try:
    df = pd.read_csv(os.path.join("dataset", "Hawker Centre Data", "DatesofHawkerCentresClosure.csv"))
    try:
        df_stalls = pd.read_csv(os.path.join("dataset", "Multiple Stalls Menu and Data", "stalls.csv"))
        merged_stalls = pd.merge(df_stalls, df, left_on='hawker_center_id', right_on='serial_no', how='inner')
    except FileNotFoundError:
        print("Warning: 'stalls.csv' not found. Stall search feature will be disabled.")
        merged_stalls = pd.DataFrame()
except FileNotFoundError:
    print("Error: 'DatesofHawkerCentresClosure.csv' not found.")
    sys.exit()


def get_coords(address):
    "Converts address/postal code to coordinates"
    try:
        geolocator = Nominatim(user_agent="sg_hawker_planner_v3")
        location = geolocator.geocode(f"{address}, Singapore")
        return (location.latitude, location.longitude) if location else None
    except:
        return None


def calculate_best_route(start_coords, hcs_df):
    "to find nearest next stop"
    route = []
    remaining = hcs_df.copy()
    current_loc = start_coords
    while not remaining.empty:
        distances = remaining.apply(lambda row: geodesic(current_loc, (row['latitude_hc'], row['longitude_hc'])).km,
                                    axis=1)
        nearest_idx = distances.idxmin()
        nearest_row = remaining.loc[nearest_idx]
        route.append(nearest_row.to_dict())
        current_loc = (nearest_row['latitude_hc'], nearest_row['longitude_hc'])
        remaining = remaining.drop(nearest_idx)
    return route


# --- MAIN PROGRAM ---
print("--- Advanced Hawker Centre & Stall Itinerary Planner ---")

#1. Get User Location
while True:
    user_addr = input("Enter your current location (e.g. 'Bedok' or '639798'): ")
    user_coords = get_coords(user_addr)
    if user_coords:
        print("Location recognized!")
        break
    print("Location not found. Try again.")

all_itineraries = []

while True:
    print("\n" + "*" * 30)
    explore_date = input("Enter the date (YYYY-MM-DD): ")
    selected_rows = []

    # 2. Select up to 5 Hawker Centres
    while len(selected_rows) < 5:
        print(f"\n--- Itinerary for {explore_date} (Stops: {len(selected_rows)}/5) ---")
        print("[1] Search Hawker Centre Name  [2] Search Stall Name/Number  [done] Finish Selection")
        search_mode = input("Option: ").strip().lower()

        if search_mode == 'done':
            if selected_rows:
                break
            else:
                print("Pick at least one!"); continue

        query = input("Enter search term: ").strip()
        matches = pd.DataFrame()

        if search_mode == '1':
            matches = df[df['name'].str.contains(query, case=False, na=False)]
        elif search_mode == '2' and not merged_stalls.empty:
            matches = merged_stalls[merged_stalls['stall_name'].str.contains(query, case=False, na=False)]
            if len(matches) > 10:
                print(f"Found {len(matches)} stalls. Filter by location:")
                locs = matches['name'].unique()
                for i, l in enumerate(locs, 1): print(f"{i}. {l}")
                try:
                    matches = matches[matches['name'] == locs[int(input("Selection: ")) - 1]]
                except:
                    continue

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
                    selected_rows.append(matches.iloc[i])
                    print(f"Added: {matches.iloc[i]['name']}")
        except:
            print("Invalid selection.")

    # 3. Calculate Initial Best Route
    selected_df = pd.DataFrame(selected_rows).drop_duplicates(subset=['serial_no'])
    itinerary = calculate_best_route(user_coords, selected_df)

    # 4. Edit Loop
    while True:
        print("\n--- CURRENT ITINERARY ---")
        for i, hc in enumerate(itinerary, 1): print(f"{i}. {hc['name']}")

        action = input("\n[1] Finalize  [2] Reorder  [3] Remove a stop: ")

        if action == '1':
            break  # Exit the edit loop
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
        print("\n" + "#" * 50)
        print(f"FINALIZED ITINERARY FOR {explore_date}")
        print("#" * 50)
        for i, hc in enumerate(itinerary, 1):
            print(f"\nSTOP {i}: {hc['name']}")
            print(f"📍 Address: {hc['address_myenv']}")
            print(f"📸 Photo: {hc['photourl']}")
            print(f"🗺️  Google Map: {hc['google_3d_view']}")
            print("-" * 30)

        all_itineraries.append({'date': explore_date, 'route': itinerary})

        # 6. Exit Strategy
    cont = input("\nPlan another itinerary for a different date? (yes/no): ").lower()
    if cont != 'yes':
        print("\nAll plans finalized. Have a great time exploring Singapore's delicacy!")
        break

