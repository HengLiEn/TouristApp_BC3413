# this one for integratioin with nicole , felicia and rest - don consider yet
# # Example usage for integration with other modules
# def get_cuisine_filtered_data(cuisines: List[str],
#                               dietary: List[str] = None,
#                               allergens: List[str] = None) -> pd.DataFrame:
#     """
#     Helper function for other modules to get cuisine-filtered data
#
#     Args:
#         cuisines: List of cuisine types (e.g., ['Chinese', 'Malay'])
#         dietary: List of dietary restrictions (e.g., ['vegetarian', 'halal'])
#         allergens: List of allergens to avoid (e.g., ['Dairy'])
#
#     Returns:
#         Filtered DataFrame ready for price/rating filtering
#
#     Example:
#         from feature_cuisine import get_cuisine_filtered_data
#
#         # In Saachee's module
#         data = get_cuisine_filtered_data(
#             cuisines=['Chinese', 'Malay'],
#             dietary=['halal']
#         )
#         # Now apply price/rating filters
#
#         # In Nicole's module
#         data = get_cuisine_filtered_data(
#             cuisines=['Western', 'Japanese']
#         )
#         # Now use for itinerary generation
#     """
#     handler = CuisineFeatureHandler()
#     handler.load_data()
#
#     preferences = CuisinePreferences(
#         cuisines=cuisines,
#         dietary_restrictions=dietary or [],
#         allergens_to_avoid=allergens or []
#     )
#
#     return handler.get_filtered_items(preferences)
