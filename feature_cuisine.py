"""
Feature: Cuisine Preferences Module for TouristApp_BC3413
Author: Li En
Project: Singapore Tourist App BC3413
"""

import pandas as pd
import os
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class CuisinePreferences:
    """User's cuisine preferences - ONLY food-related attributes"""
    cuisines: List[str] = None  # e.g., ['Chinese', 'Malay', 'Indian']
    dietary_restrictions: List[str] = None  # e.g., ['vegetarian', 'halal']
    allergens_to_avoid: List[str] = None  # e.g., ['Dairy', 'Nuts']

    def __post_init__(self):
        if self.cuisines is None:
            self.cuisines = []
        if self.dietary_restrictions is None:
            self.dietary_restrictions = []
        if self.allergens_to_avoid is None:
            self.allergens_to_avoid = []


class CuisineFeatureHandler:
    """Main class for handling cuisine preferences in the TouristApp"""

    def __init__(self, project_root: str = None):
        """
        Initialize the cuisine handler

        Args:
            project_root: Path to project root (defaults to current directory)
        """
        if project_root is None:
            project_root = os.path.dirname(os.path.abspath(__file__))

        self.project_root = project_root
        self.data_dir = os.path.join(project_root, 'dataset', 'Multiple Stalls Menu and Data')
        self.menu_items_path = os.path.join(self.data_dir, 'menu_items.csv')
        self.stalls_path = os.path.join(self.data_dir, 'stalls.csv')

        self.menu_items_df = None
        self.stalls_df = None
        self.merged_df = None

    def load_data(self):
        """Load and merge menu items with stalls data"""
        print("🔄 Loading menu items...")
        self.menu_items_df = pd.read_csv(self.menu_items_path)

        print("🔄 Loading stalls data...")
        self.stalls_df = pd.read_csv(self.stalls_path)

        # Merge menu items with stall information
        print("🔄 Merging data...")
        self.merged_df = self.menu_items_df.merge(
            self.stalls_df,
            on='stall_id',
            how='left'
        )

        print(f"✅ Loaded {len(self.menu_items_df):,} menu items from {len(self.stalls_df):,} stalls")
        return self

    def get_available_cuisines(self) -> List[str]:
        """Get list of all available cuisine types"""
        if self.stalls_df is None:
            self.load_data()
        return sorted(self.stalls_df['cuisine_type'].unique().tolist())

    def get_available_allergens(self) -> List[str]:
        """Get list of all allergens in menu items"""
        if self.menu_items_df is None:
            self.load_data()
        allergens = self.menu_items_df['allergens'].dropna().unique()
        # Split combined allergens and flatten
        all_allergens = set()
        for allergen in allergens:
            if isinstance(allergen, str) and allergen.lower() != 'none':
                all_allergens.update([a.strip() for a in allergen.split(',')])
        return sorted(all_allergens)

    def filter_by_cuisine_preferences(self, preferences: CuisinePreferences) -> pd.DataFrame:
        """
        Filter menu items based ONLY on cuisine preferences (no price/rating)

        Args:
            preferences: CuisinePreferences object with user's choices

        Returns:
            Filtered DataFrame with matching items
        """
        if self.merged_df is None:
            self.load_data()

        df = self.merged_df.copy()

        print(f"\n🔍 Filtering by cuisine preferences...")
        print(f"Starting with: {len(df):,} items\n")

        # Filter by cuisine type
        if preferences.cuisines:
            df = df[df['cuisine_type'].isin(preferences.cuisines)]
            print(f"✅ Cuisines ({', '.join(preferences.cuisines)}): {len(df):,} items")

        # Filter by dietary restrictions
        if 'vegetarian' in preferences.dietary_restrictions:
            df = df[df['vegetarian'] == 'Yes']
            print(f"✅ Vegetarian only: {len(df):,} items")

        if 'halal' in preferences.dietary_restrictions:
            df = df[df['halal'] == 'Yes']
            print(f"✅ Halal only: {len(df):,} items")

        # Filter by allergens
        if preferences.allergens_to_avoid:
            for allergen in preferences.allergens_to_avoid:
                df = df[~df['allergens'].str.contains(allergen, case=False, na=False)]
            print(f"✅ Excluding allergens ({', '.join(preferences.allergens_to_avoid)}): {len(df):,} items")

        # Only show available items
        df = df[df['is_available'] == True]
        print(f"✅ Available items only: {len(df):,} items")

        return df

    def get_filtered_items(self, preferences: CuisinePreferences) -> pd.DataFrame:
        """
        Get all items matching preferences (for other team members to filter by price/rating)

        Args:
            preferences: User's cuisine preferences

        Returns:
            DataFrame with all matching items (includes price, rating, etc. for team)
        """
        return self.filter_by_cuisine_preferences(preferences)

    def get_statistics(self, preferences: Optional[CuisinePreferences] = None) -> Dict:
        """Get statistics about available food options"""
        if preferences:
            df = self.filter_by_cuisine_preferences(preferences)
        else:
            df = self.merged_df if self.merged_df is not None else self.load_data().merged_df

        stats = {
            'total_items': len(df),
            'total_stalls': df['stall_id'].nunique(),
            'vegetarian_items': len(df[df['vegetarian'] == 'Yes']),
            'halal_items': len(df[df['halal'] == 'Yes']),
            'items_by_cuisine': df.groupby('cuisine_type').size().to_dict()
        }

        return stats

    def display_filtered_items(self, filtered_df: pd.DataFrame, max_display: int = 20):
        """Display filtered items in a formatted way"""
        if filtered_df.empty:
            print("\n❌ No items match your cuisine preferences.")
            return

        print(f"\n{'='*80}")
        print(f"🍽️  ITEMS MATCHING YOUR CUISINE PREFERENCES")
        print(f"{'='*80}\n")
        print(f"Found {len(filtered_df):,} items. Showing first {min(max_display, len(filtered_df))}:\n")

        for idx, (_, row) in enumerate(filtered_df.head(max_display).iterrows(), 1):
            print(f"{idx}. {row['item_name']} - {row['cuisine_type']}")
            print(f"   📍 {row['stall_name']}")

            # Dietary info
            diet_info = []
            if row['vegetarian'] == 'Yes':
                diet_info.append("🌱 Vegetarian")
            if row['halal'] == 'Yes':
                diet_info.append("☪️ Halal")
            if row['allergens'] and str(row['allergens']).lower() != 'none':
                diet_info.append(f"⚠️ Contains: {row['allergens']}")

            if diet_info:
                print(f"   {' | '.join(diet_info)}")

            print()

    def export_for_team(self, preferences: CuisinePreferences, output_filename: str = 'filtered_cuisine_data.csv') -> pd.DataFrame:
        """
        Export filtered data for other team members (with all price/rating data intact)

        Args:
            preferences: User's cuisine preferences
            output_filename: Name of output file (saved in project root)

        Returns:
            Filtered DataFrame
        """
        filtered_df = self.filter_by_cuisine_preferences(preferences)

        # Save to project root
        output_path = os.path.join(self.project_root, output_filename)
        filtered_df.to_csv(output_path, index=False)

        print(f"\n💾 Exported {len(filtered_df):,} items to: {output_filename}")
        print(f"📂 Location: {output_path}")
        print(f"✅ All columns preserved for price/rating filtering by team!")

        return filtered_df


def interactive_cuisine_selector():
    """Interactive CLI for selecting cuisine preferences"""
    print("\n" + "="*80)
    print("🍜 SINGAPORE TOURIST APP - CUISINE PREFERENCES")
    print("="*80 + "\n")

    # Initialize handler
    handler = CuisineFeatureHandler()
    handler.load_data()

    # Get available cuisines
    available_cuisines = handler.get_available_cuisines()
    print("\n📋 Available Cuisines:")
    for i, cuisine in enumerate(available_cuisines, 1):
        print(f"   {i}. {cuisine}")

    # Cuisine selection
    print("\n✨ Select your preferred cuisines (comma-separated numbers, or 'all'):")
    cuisine_input = input("→ ").strip()

    if cuisine_input.lower() == 'all':
        selected_cuisines = available_cuisines
    else:
        try:
            indices = [int(x.strip()) - 1 for x in cuisine_input.split(',')]
            selected_cuisines = [available_cuisines[i] for i in indices if 0 <= i < len(available_cuisines)]
        except:
            print("⚠️ Invalid input. Using all cuisines.")
            selected_cuisines = available_cuisines

    print(f"✅ Selected: {', '.join(selected_cuisines)}")

    # Dietary restrictions
    print("\n🥗 Dietary Restrictions:")
    print("   1. Vegetarian")
    print("   2. Halal")
    print("   3. None")
    dietary_input = input("→ Select (comma-separated numbers): ").strip()

    dietary_restrictions = []
    if '1' in dietary_input:
        dietary_restrictions.append('vegetarian')
    if '2' in dietary_input:
        dietary_restrictions.append('halal')

    # Allergens
    available_allergens = handler.get_available_allergens()
    print(f"\n⚠️ Available allergens: {', '.join(available_allergens)}")
    allergen_input = input("→ Any allergens to avoid? (comma-separated, or press Enter to skip): ").strip()

    allergens_to_avoid = []
    if allergen_input:
        allergens_to_avoid = [a.strip() for a in allergen_input.split(',')]

    # Create preferences object
    preferences = CuisinePreferences(
        cuisines=selected_cuisines,
        dietary_restrictions=dietary_restrictions,
        allergens_to_avoid=allergens_to_avoid
    )

    # Get filtered items
    print("\n🔍 Finding matching items...")
    filtered_items = handler.get_filtered_items(preferences)

    # Display
    handler.display_filtered_items(filtered_items, max_display=15)

    # Show statistics
    stats = handler.get_statistics(preferences)
    print(f"\n{'='*80}")
    print("📊 STATISTICS")
    print(f"{'='*80}")
    print(f"Total matching items: {stats['total_items']:,}")
    print(f"From {stats['total_stalls']:,} different stalls")
    print(f"Vegetarian options: {stats['vegetarian_items']:,}")
    print(f"Halal options: {stats['halal_items']:,}")
    print("\nBreakdown by cuisine:")
    for cuisine, count in sorted(stats['items_by_cuisine'].items(), key=lambda x: x[1], reverse=True):
        print(f"  • {cuisine}: {count:,} items")

    # Export option
    print("\n" + "="*80)
    export_choice = input("💾 Export results for team? (y/n): ").strip().lower()
    if export_choice == 'y':
        handler.export_for_team(preferences, 'filtered_cuisine_data.csv')

    return preferences, filtered_items, handler


# Example usage for integration with other modules
def get_cuisine_filtered_data(cuisines: List[str],
                              dietary: List[str] = None,
                              allergens: List[str] = None) -> pd.DataFrame:
    """
    Helper function for other modules to get cuisine-filtered data

    Args:
        cuisines: List of cuisine types (e.g., ['Chinese', 'Malay'])
        dietary: List of dietary restrictions (e.g., ['vegetarian', 'halal'])
        allergens: List of allergens to avoid (e.g., ['Dairy'])

    Returns:
        Filtered DataFrame ready for price/rating filtering

    Example:
        from feature_cuisine import get_cuisine_filtered_data

        # In Saachee's module
        data = get_cuisine_filtered_data(
            cuisines=['Chinese', 'Malay'],
            dietary=['halal']
        )
        # Now apply price/rating filters

        # In Nicole's module
        data = get_cuisine_filtered_data(
            cuisines=['Western', 'Japanese']
        )
        # Now use for itinerary generation
    """
    handler = CuisineFeatureHandler()
    handler.load_data()

    preferences = CuisinePreferences(
        cuisines=cuisines,
        dietary_restrictions=dietary or [],
        allergens_to_avoid=allergens or []
    )

    return handler.get_filtered_items(preferences)


if __name__ == "__main__":
    # Run interactive mode when executed directly
    interactive_cuisine_selector()