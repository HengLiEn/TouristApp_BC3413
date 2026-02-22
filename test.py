
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
        Case-insensitive filtering

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

        # Filter by cuisine type (case-insensitive)
        if preferences.cuisines:
            # Convert to lowercase for case-insensitive matching
            cuisines_lower = [c.lower() for c in preferences.cuisines]
            df = df[df['cuisine_type'].str.lower().isin(cuisines_lower)]
            print(f"✅ Cuisines ({', '.join(preferences.cuisines)}): {len(df):,} items")

        # Filter by dietary restrictions (case-insensitive)
        dietary_lower = [d.lower() for d in preferences.dietary_restrictions]

        if 'vegetarian' in dietary_lower:
            df = df[df['vegetarian'].str.lower() == 'yes']
            print(f"✅ Vegetarian only: {len(df):,} items")

        if 'halal' in dietary_lower:
            df = df[df['halal'].str.lower() == 'yes']
            print(f"✅ Halal only: {len(df):,} items")

        # Filter by allergens (already case-insensitive)
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
        """Display filtered items in a formatted way - shows in PyCharm console"""
        if filtered_df.empty:
            print("\n❌ No items match your cuisine preferences.")
            print("Try selecting different cuisines or removing some restrictions.\n")
            return

        print(f"\n{'=' * 80}")
        print(f"🍽️  ITEMS MATCHING YOUR CUISINE PREFERENCES")
        print(f"{'=' * 80}\n")
        print(f"Found {len(filtered_df):,} total items. Showing first {min(max_display, len(filtered_df))}:\n")

        for idx, (_, row) in enumerate(filtered_df.head(max_display).iterrows(), 1):
            print(f"{idx}. {row['item_name']} - {row['cuisine_type']}")
            print(f"   📍 Stall: {row['stall_name']}")
            print(f"   💰 Price: ${row['price']:.2f}")
            print(f"   ⭐ Rating: {row['average_rating']:.1f}/5.0 ({row['total_reviews']} reviews)")

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

        if len(filtered_df) > max_display:
            print(f"... and {len(filtered_df) - max_display:,} more items")
            print(f"\nTip: Export to CSV to see all {len(filtered_df):,} items!")

        print(f"{'=' * 80}\n")

    def export_for_team(self, preferences: CuisinePreferences,
                        output_filename: str = 'filtered_cuisine_data.csv') -> pd.DataFrame:
        """
        Export filtered data for other team members (with all price/rating data intact)
        Also displays sample results in PyCharm console

        Args:
            preferences: User's cuisine preferences
            output_filename: Name of output file (saved in project root)

        Returns:
            Filtered DataFrame
        """
        filtered_df = self.filter_by_cuisine_preferences(preferences)

        if filtered_df.empty:
            print("\n⚠️ No data to export - no items match your preferences.")
            return filtered_df

        # Save to project root
        output_path = os.path.join(self.project_root, output_filename)
        filtered_df.to_csv(output_path, index=False)

        print(f"\n{'=' * 80}")
        print(f"💾 EXPORT COMPLETE")
        print(f"{'=' * 80}")
        print(f"✅ Exported {len(filtered_df):,} items to: {output_filename}")
        print(f"📂 Location: {output_path}")
        print(f"✅ All columns preserved for price/rating filtering by team!")

        # Show sample in console
        print(f"\n📋 SAMPLE OF EXPORTED DATA (First 5 items):")
        print(f"{'-' * 80}")

        for idx, (_, row) in enumerate(filtered_df.head(5).iterrows(), 1):
            print(f"\n{idx}. {row['item_name']} - {row['cuisine_type']}")
            print(f"   Stall: {row['stall_name']}")
            print(f"   Price: ${row['price']:.2f} | Rating: {row['average_rating']:.1f}⭐")
            if row['vegetarian'] == 'Yes':
                print(f"   🌱 Vegetarian", end='')
            if row['halal'] == 'Yes':
                print(f" | ☪️ Halal", end='')
            print()

        print(f"\n{'-' * 80}")
        print(f"Full data saved to {output_filename}")
        print(f"{'=' * 80}\n")

        return filtered_df


def interactive_cuisine_selector():
    """Interactive CLI for selecting cuisine preferences - case-insensitive"""
    print("\n" + "=" * 80)
    print("🍜 SINGAPORE TOURIST APP - CUISINE PREFERENCES")
    print("=" * 80 + "\n")

    # Initialize handler
    handler = CuisineFeatureHandler()
    handler.load_data()

    # Get available cuisines
    available_cuisines = handler.get_available_cuisines()
    print("\n📋 Available Cuisines:")
    for i, cuisine in enumerate(available_cuisines, 1):
        print(f"   {i}. {cuisine}")

    # Cuisine selection
    print("\n✨ Select your preferred cuisines:")
    print("   • Enter numbers (comma-separated): e.g., 2,10,17")
    print("   • Or type cuisine names: e.g., chinese,malay")
    print("   • Or type 'all' for all cuisines")
    cuisine_input = input("→ ").strip()

    if cuisine_input.lower() == 'all':
        selected_cuisines = available_cuisines
    elif cuisine_input.replace(',', '').replace(' ', '').isdigit():
        # Number input
        try:
            indices = [int(x.strip()) - 1 for x in cuisine_input.split(',')]
            selected_cuisines = [available_cuisines[i] for i in indices if 0 <= i < len(available_cuisines)]
        except:
            print("⚠️ Invalid input. Using all cuisines.")
            selected_cuisines = available_cuisines
    else:
        # Name input (case-insensitive)
        input_cuisines = [c.strip().lower() for c in cuisine_input.split(',')]
        available_lower = {c.lower(): c for c in available_cuisines}
        selected_cuisines = []
        for input_cuisine in input_cuisines:
            if input_cuisine in available_lower:
                selected_cuisines.append(available_lower[input_cuisine])
            else:
                print(f"⚠️ '{input_cuisine}' not found, skipping...")

        if not selected_cuisines:
            print("⚠️ No valid cuisines found. Using all cuisines.")
            selected_cuisines = available_cuisines

    print(f"✅ Selected: {', '.join(selected_cuisines)}")

    # Dietary restrictions
    print("\n🥗 Dietary Restrictions:")
    print("   1. Vegetarian")
    print("   2. Halal")
    print("   3. None")
    dietary_input = input("→ Select (comma-separated numbers or names): ").strip().lower()

    dietary_restrictions = []
    if '1' in dietary_input or 'veg' in dietary_input:
        dietary_restrictions.append('vegetarian')
    if '2' in dietary_input or 'halal' in dietary_input:
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
    print("\n" + "=" * 80)
    filtered_items = handler.get_filtered_items(preferences)

    # Display in console
    handler.display_filtered_items(filtered_items, max_display=20)

    # Show statistics
    stats = handler.get_statistics(preferences)
    print(f"{'=' * 80}")
    print("📊 STATISTICS")
    print(f"{'=' * 80}")
    print(f"Total matching items: {stats['total_items']:,}")
    print(f"From {stats['total_stalls']:,} different stalls")
    print(f"🌱 Vegetarian options: {stats['vegetarian_items']:,}")
    print(f"☪️ Halal options: {stats['halal_items']:,}")
    print("\n📈 Breakdown by cuisine:")
    for cuisine, count in sorted(stats['items_by_cuisine'].items(), key=lambda x: x[1], reverse=True):
        print(f"  • {cuisine}: {count:,} items")

    # Export option
    print("\n" + "=" * 80)
    export_choice = input("💾 Export results for team? (y/n): ").strip().lower()
    if export_choice in ['y', 'yes']:
        handler.export_for_team(preferences, 'filtered_cuisine_data.csv')

    print("\n✅ Session complete! Results are displayed above.")
    print("=" * 80 + "\n")

    return preferences, filtered_items, handler