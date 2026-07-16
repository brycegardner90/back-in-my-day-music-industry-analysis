"""
01_load_sqlite.py

Loads all raw CSVs in csv/ into a single SQLite database (back_in_my_day.db)
at the project root. Run this before 02_compute_decade_metrics.py.

Note: the DB is built in local scratch space and then copied into the project
folder, because writing/indexing a SQLite file directly on the mounted project
drive can hit disk I/O errors (the mount doesn't reliably support the file
locking SQLite needs for multi-page writes).
"""
import sqlite3
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV_DIR = PROJECT_ROOT / "csv"
DB_PATH = PROJECT_ROOT / "back_in_my_day.db"
SCRATCH_DB_PATH = Path("/tmp/back_in_my_day_build.db")

import pandas as pd


def load_hot100(conn):
    df = pd.read_csv(CSV_DIR / "hot100_full_1958_present.csv", parse_dates=["chart_date"])
    df.to_sql("hot100_weekly", conn, if_exists="replace", index=False)
    print(f"  hot100_weekly: {len(df):,} rows")


def load_billboard200(conn):
    df = pd.read_csv(CSV_DIR / "billboard200_full_1967_present.csv", parse_dates=["chart_date"])
    df.to_sql("billboard200_weekly", conn, if_exists="replace", index=False)
    print(f"  billboard200_weekly: {len(df):,} rows")


def load_album_sales(conn):
    df = pd.read_csv(CSV_DIR / "album_sales_top50_by_decade.csv")
    df.to_sql("album_sales_decade", conn, if_exists="replace", index=False)
    print(f"  album_sales_decade: {len(df):,} rows")


def load_riaa_certifications(conn):
    counts = pd.read_csv(CSV_DIR / "riaa_artist_certified_counts.csv", encoding="utf-8-sig")
    counts.to_sql("riaa_artist_certified_counts", conn, if_exists="replace", index=False)
    print(f"  riaa_artist_certified_counts: {len(counts):,} rows")

    albums = pd.read_csv(CSV_DIR / "riaa_top100_artists_certified_albums.csv", encoding="utf-8-sig")
    albums["cert_date_parsed"] = pd.to_datetime(albums["CertDate"], format="%d-%b-%y", errors="coerce")
    albums.loc[albums["cert_date_parsed"].dt.year > 2026, "cert_date_parsed"] -= pd.DateOffset(years=100)
    albums["cert_decade"] = (albums["cert_date_parsed"].dt.year // 10 * 10).astype("Int64").astype(str) + "s"
    albums.to_sql("riaa_certified_albums", conn, if_exists="replace", index=False)
    print(f"  riaa_certified_albums: {len(albums):,} rows")

    top100 = pd.read_csv(CSV_DIR / "riaa_top100_albums_attributes.csv", encoding="utf-8-sig")
    top100.to_sql("riaa_top100_albums_attributes", conn, if_exists="replace", index=False)
    print(f"  riaa_top100_albums_attributes: {len(top100):,} rows")


def load_riaa_revenue(conn):
    df = pd.read_csv(CSV_DIR / "riaa_revenue_benchmarks.csv")
    df.to_sql("riaa_revenue_benchmarks", conn, if_exists="replace", index=False)
    print(f"  riaa_revenue_benchmarks: {len(df):,} rows")


def main():
    if SCRATCH_DB_PATH.exists():
        SCRATCH_DB_PATH.unlink()
    conn = sqlite3.connect(SCRATCH_DB_PATH)
    print(f"Building DB in scratch space: {SCRATCH_DB_PATH}")
    load_hot100(conn)
    load_billboard200(conn)
    load_album_sales(conn)
    load_riaa_certifications(conn)
    load_riaa_revenue(conn)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_hot100_date ON hot100_weekly(chart_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hot100_performer ON hot100_weekly(performer)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_b200_date ON billboard200_weekly(chart_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_b200_performer ON billboard200_weekly(performer)")
    conn.commit()
    conn.close()

    # Overwrite in place rather than unlink+copy: files in the connected project
    # folder can't be deleted/renamed once written, but overwriting content is fine.
    # Use the shell `cp` + `sync` rather than shutil.copyfile: on this project's
    # mounted network drive, shutil's buffered copy has left behind a truncated
    # (0-byte-readable) file even when `ls` reported the correct size, while a
    # plain `cp` followed by `sync` verified byte-identical (md5) reliably.
    import subprocess
    subprocess.run(["cp", str(SCRATCH_DB_PATH), str(DB_PATH)], check=True)
    subprocess.run(["sync"], check=True)
    print(f"Copied final DB to {DB_PATH}")


if __name__ == "__main__":
    main()
