This is a README file 

## Project Structure

├── main.py                  # Entry point — orchestrates all features
├── saachees_file.py         # User authentication and profile data access
├── feature_cuisines.py      # Cuisine preferences and allergen filtering
├── feature_pricing.py       # Price-based food recommendations
├── features_closure.py      # Hawker centre closure date filtering
├── features_location.py     # Geolocation, routing, and itinerary building
├── features_reviews.py      # Reading and writing stall reviews
├── tourist_profiles.db      # SQLite database for user profiles
└── dataset/
    ├── Multiple Stalls Menu and Data/
    │   ├── menu_items.csv
    │   ├── stalls.csv
    │   └── reviews.csv
    └── Hawker Centre Data/
        └── DatesofHawkerCentresClosure.csv

## Features

- **Account system** — create an account and log in with saved preferences
- **Cuisine recommendations** — filter stalls by cuisine type and allergens
- **Price recommendations** — find stalls within a budget, food or drink
- **Itinerary planner** — builds a walkable route from your saved or recommended stalls
- **Reviews** — read, write, and mark reviews as helpful
- **Trip date filtering** — automatically excludes hawker centres closed during your trip
- **Location-aware** — uses Singapore OneMap API to resolve postal codes and addresses
