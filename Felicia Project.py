# my code asks tourists what is the min and max price they prefer and if they are looking at specifically Food/Drinks/Both
import pandas as pd
import sqlite3


class DataManager:
    def __init__(self):
        self.dataframes = []
        self.file_names = []
        self.merge_keys = []

    def load_csv_files(self):
        file_order = ["1st", "2nd", "3rd"]

        for order in file_order:
            filename = input(f"Enter {order} CSV file you want to merge (or X to stop): ")

            if filename.upper() == "X":
                break

            try:
                df = pd.read_csv(filename)
                self.dataframes.append(df)
                self.file_names.append(filename)
                print(f"{filename} loaded successfully.\n")

            except Exception as e:
                print(f"Error loading file: {e}\n")

        if len(self.dataframes) < 2:
            print("At least 2 CSV files are required to merge.")
            return None

        return self.merge_dataframes()

    def ask_merge_columns(self):
        """
        Ask user which columns to use for merging between files.
        """

        print("\n--- Column Selection for Merging ---\n")

        for i in range(len(self.dataframes) - 1):
            print(f"Merging File {i+1} ({self.file_names[i]}) "
                  f"WITH File {i+2} ({self.file_names[i+1]})")

            print("Columns in File 1:")
            print(self.dataframes[i].columns.tolist())

            col1 = input("Enter column name from File 1 to merge on: ")

            print("\nColumns in File 2:")
            print(self.dataframes[i + 1].columns.tolist())

            col2 = input("Enter column name from File 2 to merge on: ")

            self.merge_keys.append((col1, col2))
            print("\n")

    def merge_dataframes(self):
        print("Setting merge columns...\n")

        self.ask_merge_columns()

        merged_df = self.dataframes[0]

        for i in range(1, len(self.dataframes)):
            left_key, right_key = self.merge_keys[i - 1]

            merged_df = pd.merge(
                merged_df,
                self.dataframes[i],
                how="inner",
                left_on=left_key,
                right_on=right_key
            )

        print("Merge completed successfully!\n")
        return merged_df


class DatabaseManager:
    def __init__(self, db_name="hawker_data.db"):
        self.conn = sqlite3.connect(db_name)

    def save_to_database(self, df, table_name):
        df.to_sql(table_name, self.conn, if_exists="replace", index=False)
        print(f"Data saved into SQLite database table '{table_name}'.\n")


class Tourist:
    def __init__(self, min_price, max_price, preference):
        self.min_price = min_price
        self.max_price = max_price
        self.preference = preference.upper()


def main():
    data_manager = DataManager()
    db_manager = DatabaseManager()

    full_data = data_manager.load_csv_files()

    if full_data is None:
        return

    db_manager.save_to_database(full_data, "merged_data")

    while True:
        try:
            min_price = float(input("Enter minimum price: "))
            max_price = float(input("Enter maximum price: "))

            preference = input("Are you looking for Food (F), Drinks (D), or Both (B)? ").upper()

            # ---- Filtering ----
            filtered = full_data[
                (full_data["price"] >= min_price) &
                (full_data["price"] <= max_price)
                ]

            if preference == "F":
                filtered = filtered[filtered["category_id"] == 1]

            elif preference == "D":
                filtered = filtered[filtered["category_id"] == 2]

            elif preference == "B":
                filtered = filtered[filtered["category_id"].isin([1, 2])]

            else:
                print("Invalid preference.")
                continue

            # ---- Display Results ----
            columns_to_show = ["item_name", "price", "center_name", "stall_name"]
            existing_columns = [col for col in columns_to_show if col in filtered.columns]

            if filtered.empty:
                print("\nNo matching results found.\n")
            else:
                print("\nRecommended Options:\n")
                print(filtered[existing_columns].to_string(index=False))

            # ---- Ask If They Want Another Recommendation ----
            again = input("\nWould you like another recommendation? (Y/N): ").upper()

            if again == "Y":
                continue
            elif again == "N":
                print("Exiting recommendation system...\n")
                break
            else:
                print("Invalid input. Exiting by default.")
                break

        except ValueError:
            print("Invalid input. Please enter numbers correctly.\n")


if __name__ == "__main__":
    main()