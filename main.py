import feature_cuisine
# import feature_closing
# import feature_location


def display_main_menu():
    print("\n" + "=" * 50)
    print("   WELCOME TO HAWKER CENTER GUIDE")
    print("=" * 50)
    print("\n1. View Hawker Center Closing Dates")
    print("2. Plan Your Visit (Location & Itinerary)")
    print("3. Browse Menu & Get Recommendations")
    print("4. Exit")
    print("-" * 50)


    while True:
        display_main_menu()
        choice = input("\nSelect an option (1-4): ")

        if choice == '1':
            feature_closing.run_closing_dates()  #
        elif choice == '2':
            feature_location.run_itinerary()  #
        elif choice == '3':
            feature_cuisine.run_menu_recommendations()  # lien function
        elif choice == '4':
            print("Thank you for using Hawker Guide!")
            break
        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":
    main()