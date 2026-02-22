import pandas as pd

pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)

# 1️⃣ Load the CSV files
menu_items = pd.read_csv("menu_items (1).csv")
stalls = pd.read_csv("stalls.csv")
hawker_centers = pd.read_csv("hawker_centers.csv")

# 2️⃣ Merge menu_items with stalls using 'stall_id'
menu_stalls = pd.merge(
    menu_items,
    stalls,
    on="stall_id",
    how="inner"
)

# 3️⃣ Merge the result with hawker_centers
# Using hawker_id (from stalls) and center_id (from hawker_centres)
full_data = pd.merge(
    menu_stalls,
    hawker_centers,
    left_on="hawker_center_id",
    right_on="center_id",
    how="inner"
)

# 4️⃣ Display result
print(full_data.head())

# tourist input
budget = float(input("Enter your budget: "))

recommended = full_data[full_data["price"] <= budget]

print(recommended[["stall_name", "center_name", "item_name", "price" ]])


