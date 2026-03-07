This is a README file 

## Project Structure

1. main.py                  # Entry point — orchestrates all features
2. feature_onboarding.py         # User authentication and profile data access
3. feature_cuisines.py      # Cuisine preferences and allergen filtering
4. feature_pricing.py       # Price-based food recommendations
5. features_closure.py      # Hawker centre closure date filtering
6. features_location.py     # Geolocation, routing, and itinerary building
7. features_reviews.py      # Reading and writing stall reviews
8. tourist_profiles.db      # SQLite database for user profiles
9. dataset/
    1. Multiple Stalls Menu and Data/
      i.   menu_items.csv
      ii.  stalls.csv
      iii. reviews.csv

    2. Hawker Centre Data/
      i. DatesofHawkerCentresClosure.csv

## Features

- **Account system** — create an account and log in with saved preferences
- **Cuisine recommendations** — filter stalls by cuisine type and allergens
- **Price recommendations** — find stalls within a budget, food or drink
- **Itinerary planner** — builds a walkable route from your saved or recommended stalls
- **Reviews** — read, write, and mark reviews as helpful
- **Trip date filtering** — automatically excludes hawker centres closed during your trip
- **Location-aware** — uses Singapore OneMap API to resolve postal codes and addresses
