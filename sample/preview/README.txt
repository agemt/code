Preview ingestion files

All files in this folder are comma-separated text and are usable by lookup ingestion.

Files with title row (engine/title row present):
- with_title_B3_B4_B6.txt
- with_title_B3_B6.txt
- with_title_B4_B6.txt

Files without title row (first row starts with test labels):
- without_title_B3_B4_B6.txt
- without_title_B3_B6.txt
- without_title_B4_B6.txt

Combinations covered:
- B3 + B4 + B6
- B3 + B6
- B4 + B6

Notes:
- Date row uses ISO-like timestamps.
- Take-off columns include labels containing "Take" so they are detected by lookup logic.
- Engine fallback for no-title files resolves to file stem during preview/ingestion.
