"""
Feature: Cuisine Preferences Module for TouristApp_BC3413
Author: LiEn
Project: Singapore Tourist App BC3413
"""

import pandas as pd
import os
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class CuisinePreferences:
    #reason of branching this to none instead of empty list such that it doesn append to the same instance by accident.
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






if __name__ == "__main__":
    # Run interactive mode when executed directly
    interactive_cuisine_selector()
