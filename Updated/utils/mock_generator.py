import os
import random
import datetime

def create_mock_files():
    base_dir = r"c:\application\mock_raw_files"
    os.makedirs(base_dir, exist_ok=True)
    
    # 1. Standard layout files (WW342A to WW342D)
    standard_engines = ["WW342A", "WW342B", "WW342C"]
    for idx, engine in enumerate(standard_engines):
        file_path = os.path.join(base_dir, f"test_run_{engine}.txt")
        date_str = (datetime.date(2026, 6, 1) + datetime.timedelta(days=idx)).strftime("%Y-%m-%d")
        
        # Structure:
        # Row 1 (Empty)
        # Row 2 (Engine Name)
        # Row 3 (Keyword)
        # Row 4 (Date)
        # Row 5 (Scope)
        # Row 6+ (Params: A01111 is W2K3, A01112 is FPR, A01113 is PO/PBAR_psia)
        content = [
            ["", "", "", "", "", ""],
            ["", "", engine, "", engine, ""], # Engine Name in Row 2
            ["", "", "Takeoff", "G", "Start", "G"], # Takeoff vs Start keyword
            ["", "", date_str, "", date_str, ""],
            ["", "", "Take_Off", "", "Min_Idle", ""],
            ["W2K3", "", str(850 + idx * 5 + random.randint(-10, 10)), "G", "820", "G"],
            ["FPR", "", str(1.45 + idx * 0.01 + random.uniform(-0.02, 0.02)), "G", "1.30", "G"],
            ["PO/PBAR_psia", "", str(14.2 + random.uniform(-0.1, 0.2)), "G", "14.0", "G"]
        ]
        
        write_csv(file_path, content)

    # 2. Fallback layout files (stored in folder-named directories)
    fallback_engines = ["WW342X", "WW342Y"]
    for idx, engine in enumerate(fallback_engines):
        eng_dir = os.path.join(base_dir, engine)
        os.makedirs(eng_dir, exist_ok=True)
        file_path = os.path.join(eng_dir, "test_run_fallback.txt")
        date_str = (datetime.date(2026, 6, 10) + datetime.timedelta(days=idx)).strftime("%Y-%m-%d")
        
        # Structure (Engine Row is keyword, fallback date is Row 3, Engine name is folder):
        # Row 1 (Empty)
        # Row 2 (Keyword 'Takeoff')
        # Row 3 (Date)
        # Row 4 (Scope)
        # Row 5+ (Params)
        content = [
            ["", "", "", "", "", ""],
            ["", "", "Takeoff", "G", "Start", "G"], # Keyword in Row 2
            ["", "", date_str, "", date_str, ""], # Date in Row 3
            ["", "", "Take_Off", "", "Min_Idle", ""], # Scope in Row 4
            ["W2K3", "", str(910 + idx * 8 + random.randint(-15, 15)), "G", "830", "G"],
            ["FPR", "", str(1.58 + idx * 0.01 + random.uniform(-0.03, 0.03)), "G", "1.35", "G"],
            ["PO/PBAR_psia", "", str(14.6 + random.uniform(-0.2, 0.2)), "G", "14.1", "G"]
        ]
        
        write_csv(file_path, content)
        
    print(f"Generated mock raw test files in: {base_dir}")

def write_csv(file_path, content):
    import csv
    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerows(content)

if __name__ == "__main__":
    create_mock_files()
