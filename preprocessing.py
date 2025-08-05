"""
Run this script first to preprocess the household power consumption data
and save it in a clean CSV format for further analysis or benchmarking.
"""
import pandas as pd 

# === Step 1: Load the data ===
df = pd.read_csv("household_power_consumption.txt", sep=";", low_memory=False)
original_row_count = len(df)

# === Step 2: Drop rows with any missing values ===
df = df.dropna()
after_dropna_count = len(df)

# === Step 3: Combine Date and Time into a single ISO 8601 timestamp column ===
df["timestamp"] = pd.to_datetime(df["Date"] + " " + df["Time"], format="%d/%m/%Y %H:%M:%S")
df = df.drop(columns=["Date", "Time"])  # Drop original columns

# === Step 4: Reorder columns to put timestamp first ===
cols = ["timestamp"] + [col for col in df.columns if col != "timestamp"]
df = df[cols]

# === Step 5: Convert all remaining columns to numeric (just in case) ===
for col in df.columns[1:]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# Optional: Drop rows with any remaining NaNs after conversion
df = df.dropna()
final_row_count = len(df)

# === Step 6: Save to CSV ===
df.to_csv("cleaned_power_data.csv", index=False)

# === Step 7: Report row counts ===
total_removed = original_row_count - final_row_count

print("Data cleaned and saved as 'cleaned_power_data.csv'")
print(f"Original rows (excluding header): {original_row_count}")
print(f"Rows after dropna (initial): {after_dropna_count}")
print(f"Final rows after full cleaning: {final_row_count}")
print(f"Total rows removed: {total_removed}")