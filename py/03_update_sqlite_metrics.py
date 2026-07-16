"""
03_update_sqlite_metrics.py

Adds the computed metrics tables (from 02_compute_decade_metrics.py) into
back_in_my_day.db. Run after 02_compute_decade_metrics.py.

Same scratch-then-copy pattern as 01_load_sqlite.py: SQLite writes directly
to the mounted project drive have proven unreliable (silent truncation on
large files), so the DB is rebuilt/updated in local scratch space and moved
into place with `cp` + `sync` at the end, which verified byte-identical.
"""
import sqlite3
import subprocess
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV_DIR = PROJECT_ROOT / "csv"
DB_PATH = PROJECT_ROOT / "back_in_my_day.db"
SCRATCH_DB_PATH = Path("/tmp/back_in_my_day_build.db")


def main():
    if not SCRATCH_DB_PATH.exists():
        raise SystemExit(
            f"{SCRATCH_DB_PATH} not found — run 01_load_sqlite.py first "
            "(it builds the base DB in scratch space before this script adds to it)."
        )

    conn = sqlite3.connect(SCRATCH_DB_PATH)

    tables = {
        "decade_metrics_summary": "decade_metrics_summary.csv",
        "artist_decade_hot100_summary": "artist_decade_hot100_summary.csv",
        "new_artist_entries_by_year": "new_artist_entries_by_year.csv",
    }
    for table_name, csv_name in tables.items():
        df = pd.read_csv(CSV_DIR / csv_name)
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        print(f"  {table_name}: {len(df):,} rows")

    conn.commit()
    conn.close()

    subprocess.run(["cp", str(SCRATCH_DB_PATH), str(DB_PATH)], check=True)
    subprocess.run(["sync"], check=True)
    print(f"Updated DB copied to {DB_PATH}")


if __name__ == "__main__":
    main()
