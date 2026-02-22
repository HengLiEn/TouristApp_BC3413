import pandas as pd
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
import sys

# Load the dataset
try:
    df = pd.read_csv('DatesofHawkerCentresClosure.csv')
except FileNotFoundError:
    print("Error: 'DatesofHawkerCentresClosure.csv' not found.")
    sys.exit()


def get_coords(address):
    """Converts address/postal code to coordinates"""
    try:
        # Using a unique user_agent is good practice
        geolocator = Nominatim(user_agent="sg_hawker_planner_v2")
        location = geolocator.geocode(f"{address}, Singapore")
        if location:
            return (location.latitude, location.longitude)
        return None
    except Exception as e:
        print(f"Geocoding error: {e}")
        return None


def calculate_best_route(start_coords, hcs_df):
    """Greedy algorithm to find the nearest next stop"""
    route = []
    remaining = hcs_df.copy()
    current_loc = start_coords

    # FIX: Use .empty instead of just the variable name
    while not remaining.empty:
        # Calculate distance from current_loc to all rows in 'remaining'
        distances = remaining.apply(
            lambda row: geodesic(current_loc, (row['latitude_hc'], row['longitude_hc'])).km,
            axis=1
        )
        nearest_idx = distances.idxmin()
        nearest_row = remaining.loc[nearest_idx]

        route.append(nearest_row.to_dict())
        current_loc = (nearest_row['latitude_hc'], nearest_row['longitude_hc'])

        # Remove the visited centre from the list
        remaining = remaining.drop(nearest_idx)

    return route


# 1. Get User Location
print("--- Hawker Centre Itinerary Planner ---")
while True:
    user_addr = input("Enter your current location (e.g. 'Bedok' or '639798'): ")
    user_coords = get_coords(user_addr)
    if user_coords:
        print(f"Location recognized!")
        break
    print("Location not found. Please try another address or a 6-digit postal code.")

# 2. Select up to 5 Hawker Centres
selected_rows = []
while len(selected_rows) < 5:
    query = input(f"\nSearch for a Hawker Centre (Picked {len(selected_rows)}/5, or type 'done'): ").strip()
    if query.lower() == 'done':
        if len(selected_rows) > 0:
            break
        else:
            print("Please pick at least one!"); continue

    # Search the 'name' column
    matches = df[df['name'].str.contains(query, case=False, na=False)]

    if matches.empty:
        print(f"'{query}' does not exist in our database. Please try another.")
    else:
        print("\nMatching Hawker Centres:")
        for idx, row in matches.iterrows():
            print(f"ID {idx}: {row['name']}")

        choice = input("\nEnter the ID of the exact location to add (or press Enter to search again): ")
        try:
            if choice.strip() == "": continue
            choice_int = int(choice)
            if choice_int in matches.index:
                selected_rows.append(df.loc[choice_int])
                print(f"Added: {df.loc[choice_int]['name']}")
            else:
                print("That ID was not in the search results.")
        except ValueError:
            print("Please enter a valid numeric ID.")

# 3. Calculate Initial Best Route
selected_df = pd.DataFrame(selected_rows)
itinerary = calculate_best_route(user_coords, selected_df)

# 4 & 6. Edit Loop (User can edit multiple times)
while True:
    print("\n" + "=" * 50)
    print("YOUR CURRENT ITINERARY")
    print("=" * 50)
    for i, hc in enumerate(itinerary, 1):
        print(f"{i}. {hc['name']}")

    print("\nOptions: [1] Finalize  [2] Reorder Itinerary")
    action = input("Select an option: ")

    if action == '2':
        print("\nEnter the new order by numbers (e.g., if you have 3 stops and want to go to #2 first, type '2,1,3'):")
        new_order = input("New order: ")
        try:
            indices = [int(x.strip()) - 1 for x in new_order.split(',')]
            if len(indices) != len(itinerary):
                print(f"Please include all {len(itinerary)} stops.")
                continue
            itinerary = [itinerary[i] for i in indices]
        except Exception:
            print("Invalid format. Please use numbers and commas.")
    elif action == '1':
        break
    else:
        print("Invalid selection.")

# 5. Final Display
print("\n" + "#" * 50)
print("FINALIZED ITINERARY")
print("#" * 50)
for i, hc in enumerate(itinerary, 1):
    print(f"\nSTOP {i}: {hc['name']}")
    print(f"📍 Address: {hc['address_myenv']}")
    print(f"📸 Photo: {hc['photourl']}")
    print(f"🗺️  Google Map: {hc['google_3d_view']}")
    print("-" * 30)

print("\nItinerary Complete! Safe travels and enjoy the food!")