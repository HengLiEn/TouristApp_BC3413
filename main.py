import feature_cuisines
import saachees_file
# import feature_closing
# import feature_location


def display_main_menu():
    """Display the menu options"""
    print("\n" + "=" * 50)
    print("   WELCOME TO HAWKER CENTER GUIDE")
    print("=" * 50)
    print("\n1. View Hawker Center Closing Dates")
    print("2. Plan Your Visit (Location & Itinerary)")
    print("3. Browse Menu & Get Recommendations")
    print("4. Exit")
    print("-" * 50)


def main():
    """Main program loop"""
    da = saachees_file.TouristProfileDA()

    while True:
        print("\n=== Tourist App ===")
        print("1) Create Account")
        print("2) Login")
        print("0) Exit")

        choice = input("Choose: ").strip()

        if choice == "1":
            saachees_file.create_account(da)
        elif choice == "2":
            saachees_file.login(da)
        elif choice == "0":
            break
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()