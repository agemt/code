import os
import csv
import pandas as pd

# ==========================================
# USER CONFIGURATION
# ==========================================
PATHS_EXCEL = "paths.xlsx"      # Input configuration Excel file
PARAMS_TXT = "params.txt"       # List of parameters to find
OUTPUT_FILE = "output.xlsx"

KEYWORD_Y = "Take"              # keyword to match in the lookup row

# ==========================================
# LOAD TXT PARAMETERS
# ==========================================
def load_params(txt_path):
    items = []
    with open(txt_path, 'r', encoding='utf-8-sig') as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(line)
    return items

# ==========================================
# LOAD LOOKUP CONFIGURATION FROM EXCEL
# ==========================================
def load_config_excel(excel_path):
    config_df = pd.read_excel(excel_path)
    config_df.columns = config_df.columns.str.strip().str.lower()

    # Locate column names dynamically
    path_col = next((c for c in config_df.columns if "path" in c), None)
    lookup_col = next((c for c in config_df.columns if "lookup" in c), None)
    date_col = next((c for c in config_df.columns if "date" in c), None)

    if not path_col or not lookup_col or not date_col:
        print("❌ 'paths.xlsx' must contain columns named 'Path', 'Lookup', and 'Date'.")
        return []

    config_list = []
    for idx, row in config_df.iterrows():
        path = str(row[path_col]).strip()
        lookup = str(row[lookup_col]).strip()
        date_row = str(row[date_col]).strip()

        if path and lookup and date_row and path.lower() != "nan" and lookup.lower() != "nan" and date_row.lower() != "nan":
            config_list.append((path, lookup, date_row))

    return config_list

# ==========================================
# LOAD DATA FILE (Excel or CSV) WITH ROBUST ENCODING
# ==========================================
def load_data(path):
    ext = os.path.splitext(path)[1].lower()

    if ext == '.xlsx':
        try:
            return pd.read_excel(path, engine='openpyxl'), "Excel (.xlsx)"
        except Exception:
            pass

    if ext == '.xls':
        try:
            return pd.read_excel(path, engine='xlrd'), "Excel (.xls)"
        except Exception:
            pass

    try:
        df = pd.read_csv(
            path, sep=None, engine='python',
            quoting=csv.QUOTE_NONE, escapechar='\\',
            on_bad_lines='skip', encoding='utf-8-sig'
        )
        return df, "CSV/TXT (UTF-8)"
    except Exception:
        pass

    try:
        df = pd.read_csv(
            path, sep=None, engine='python',
            quoting=csv.QUOTE_NONE, escapechar='\\',
            on_bad_lines='skip', encoding='utf-16'
        )
        return df, "CSV/TXT (UTF-16)"
    except Exception:
        pass

    try:
        df = pd.read_csv(
            path, sep=None, engine='python',
            quoting=csv.QUOTE_NONE, escapechar='\\',
            on_bad_lines='skip', encoding='latin1',
            encoding_errors='ignore'
        )
        return df, "CSV/TXT (Latin1 Fallback)"
    except Exception:
        return None, "Failed to Parse"


# ==========================================
# PROCESS A SINGLE FILE
# ==========================================
def process_file(path, lookup_row_val, date_row_val, params, current_idx, total_files):
    filename = os.path.basename(path)
    print(f"[{current_idx}/{total_files}] : {filename}")

    # Safely convert target lookup row to integer index
    try:
        row_x_idx = int(float(lookup_row_val))
    except ValueError:
        print(f"  ❌ Error: Invalid row index value '{lookup_row_val}'")
        return []

    # Safely convert target date row to integer index
    try:
        date_row_idx = int(float(date_row_val))
    except ValueError:
        print(f"  ❌ Invalid row index value '{date_row_val}'")
        return []

    df, format_type = load_data(path)
    if df is None or df.empty:
        print(f"  ❌ Could not read file structure ({format_type})")
        return []

    print(f"  Format: {format_type}")
    parent = os.path.basename(os.path.dirname(path))
    output_rows = []

    # Validation bounds checking
    if row_x_idx >= len(df):
        print(f"  ⚠️ Cannot access Lookup row index {row_x_idx}.")
        return []
    if date_row_idx >= len(df):
        print(f"  ⚠️ Cannot access Date row index {date_row_idx}.")
        return []

    row_x = df.iloc[row_x_idx]

    # Target columns containing the keyword (e.g. 'Take')
    matching_cols = [
        col for col in df.columns
        if KEYWORD_Y.lower() in str(row_x[col]).lower()
    ]

    if not matching_cols:
        print(f"  ⚠️ '{KEYWORD_Y}' not found in row {row_x_idx}.")
        return []

    first_col_str = df.iloc[:, 0].astype(str).str.strip().tolist()

    # Build one row per matched column
    for col in matching_cols:
        matched_value = str(row_x[col]).replace(',', '.') if not pd.isna(row_x[col]) else None

        # Pull date cell
        raw_date = df.iloc[date_row_idx, df.columns.get_loc(col)]
        try:
            date_value = pd.to_datetime(raw_date).strftime('%Y-%m-%d %H:%M:%S') if not pd.isna(raw_date) else None
        except Exception:
            date_value = str(raw_date) if not pd.isna(raw_date) else None

        param_values = []
        for p in params:
            clean_p = str(p).strip()

            if clean_p in first_col_str:
                row_idx = first_col_str.index(clean_p)
                raw_val = df.iloc[row_idx, df.columns.get_loc(col)]

                if pd.isna(raw_val):
                    param_values.append(None)
                else:
                    # 1. Clean all leading/trailing whitespaces immediately
                    val_str = str(raw_val).strip()

                    if val_str.lower() in ["nan", "none", ""]:
                        param_values.append(None)
                    else:
                        # 2. Handle European comma decimal formats if needed
                        # If your system expects dots, comment out the next line!
                        val_str = val_str.replace(',', '.')

                        # 3. Try converting to a real number so Excel recognizes it
                        try:
                            # Standardize to dot temporarily for float conversion check
                            check_str = val_str.replace(',', '.')
                            numeric_val = float(check_str)

                            # If it's a whole number (like 5.0), keep it clean as an integer
                            if numeric_val.is_integer():
                                param_values.append(int(numeric_val))
                            else:
                                # Keep as a float number type
                                param_values.append(numeric_val)
                        except ValueError:
                            # Fallback to string if it is actual text (e.g., "OK", "Fail")
                            param_values.append(val_str)
            else:
                param_values.append(None)

        output_rows.append([parent, date_value] + param_values + [matched_value])

    print(f"  ✅ {len(matching_cols)} data columns.")
    return output_rows


# ==========================================
# MAIN EXECUTION
# ==========================================
def main():
    if not os.path.exists(PATHS_EXCEL):
        print(f"'{PATHS_EXCEL}' missing.")
        return

    if not os.path.exists(PARAMS_TXT):
        print(f"'{PARAMS_TXT}' missing.")
        return

    file_configs = load_config_excel(PATHS_EXCEL)
    params = load_params(PARAMS_TXT)

    total_files = len(file_configs)
    print(f"Loaded {len(params)} parameters from text config")
    print(f"Found {total_files} files\n")

    all_rows = []

    for idx, (path, lookup_row_val, date_row_val) in enumerate(file_configs, start=1):
        if os.path.exists(path):
            all_rows.extend(process_file(path, lookup_row_val, date_row_val, params, idx, total_files))
        else:
            print(f"[{idx}/{total_files}] Processing: {path}")
            print(f"  ❌ File path does not exist.")

    # Build final DataFrame
    header = ['Engine', 'Date_Tested'] + params + ['Perf. Point']
    out_df = pd.DataFrame(all_rows, columns=header)

    try:
        out_df.to_excel(OUTPUT_FILE, index=False)
        print(f"Finished processing {total_files} runs.")
    except Exception as e:
        print(f"Error compiling: {str(e)}")
        input('Close excel')
        try:
            out_df.to_excel(OUTPUT_FILE, index=False)
            print(f"Finished processing {total_files} runs.")
        except Exception as e:
            print(f"Error compiling: {str(e)}")

# ==========================================
# RUN
# ==========================================
if __name__ == "__main__":
    main()