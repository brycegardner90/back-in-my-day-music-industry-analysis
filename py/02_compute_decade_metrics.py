"""
02_compute_decade_metrics.py

Computes the headline Dominance & Competition and Discovery & Gatekeeping
metrics defined in the pipeline plan doc, working directly off the raw CSVs
in csv/ (reading the multi-hundred-thousand-row Hot 100 / Billboard 200
archives from the mounted project drive via pandas has proven reliable;
random-access reads of a large SQLite file over that same mount have not,
so this script avoids reading the .db back in and instead writes fresh
summary CSVs plus reloads them into the DB via 03_update_sqlite_metrics.py's
same scratch-then-copy pattern).

Outputs (written to csv/):
  - decade_metrics_summary.csv      one row per decade, headline numbers
  - artist_decade_hot100_summary.csv artist-level rollup per decade (Hot 100)
  - new_artist_entries_by_year.csv   Top 10 first-timers per year (turnover)
  - album_sales_concentration.csv   top-10/25/50 share of decade album sales
"""
import pandas as pd
import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV_DIR = PROJECT_ROOT / "csv"

DECADE_ORDER = ["1970s", "1980s", "1990s", "2000s", "2010s"]


def load_hot100():
    df = pd.read_csv(CSV_DIR / "hot100_full_1958_present.csv", parse_dates=["chart_date"])
    # restrict to the five decades this project actually compares
    df = df[df["decade"].isin(DECADE_ORDER)].copy()
    return df


def chart_share_concentration(hot100):
    """HHI + top-10%/top-1% artist share of Hot 100 chart-weeks, per decade."""
    rows = []
    artist_rows = []
    for decade, g in hot100.groupby("decade"):
        artist_weeks = g.groupby("performer").size().sort_values(ascending=False)
        total_weeks = artist_weeks.sum()
        shares = artist_weeks / total_weeks

        hhi = float((shares ** 2).sum() * 10000)  # standard 0-10,000 HHI scale

        n_artists = len(artist_weeks)
        top10pct_n = max(1, int(np.ceil(n_artists * 0.10)))
        top1pct_n = max(1, int(np.ceil(n_artists * 0.01)))
        top10pct_share = float(artist_weeks.iloc[:top10pct_n].sum() / total_weeks)
        top1pct_share = float(artist_weeks.iloc[:top1pct_n].sum() / total_weeks)

        rows.append({
            "decade": decade,
            "distinct_artists": n_artists,
            "total_chart_weeks": int(total_weeks),
            "hhi_chart_share": round(hhi, 2),
            "top10pct_artist_share_of_weeks": round(top10pct_share, 4),
            "top1pct_artist_share_of_weeks": round(top1pct_share, 4),
        })

        for artist, weeks in artist_weeks.items():
            artist_rows.append({
                "decade": decade,
                "performer": artist,
                "chart_weeks": int(weeks),
                "share_of_decade_weeks": round(weeks / total_weeks, 6),
            })

    return pd.DataFrame(rows), pd.DataFrame(artist_rows)


def number_one_longevity(hot100):
    """Avg/median weeks-at-#1 per song, and top-5-artist share of #1 weeks, per decade."""
    no1 = hot100[hot100["rank"] == 1]
    rows = []
    for decade, g in no1.groupby("decade"):
        per_song = g.groupby(["title", "performer"]).size()  # weeks at #1 for that song
        avg_weeks = float(per_song.mean())
        median_weeks = float(per_song.median())

        per_artist = g.groupby("performer").size().sort_values(ascending=False)
        total_no1_weeks = per_artist.sum()
        top5_share = float(per_artist.iloc[:5].sum() / total_no1_weeks)

        rows.append({
            "decade": decade,
            "num_number_one_songs": int(per_song.shape[0]),
            "avg_weeks_at_number_one": round(avg_weeks, 2),
            "median_weeks_at_number_one": round(median_weeks, 2),
            "top5_artist_share_of_number_one_weeks": round(top5_share, 4),
        })
    return pd.DataFrame(rows)


def new_artist_entry_rate(hot100_all_years):
    """For each year, how many distinct artists hit the Top 10 for the first time ever
    (computed across the FULL historical archive, not just the 5 comparison decades,
    so a 1970s artist charting again in the 1980s isn't miscounted as 'new')."""
    top10 = hot100_all_years[hot100_all_years["rank"] <= 10]
    first_year = top10.groupby("performer")["year"].min().rename("first_top10_year")
    counts = first_year.value_counts().sort_index()
    out = counts.reset_index()
    out.columns = ["year", "new_top10_artists"]
    return out


def turnover_by_decade(entry_rate):
    """Average new-top10-artists-per-year, rolled up to decade grain, so Power BI
    can treat turnover exactly like the other headline metrics (a plain column on
    decade_metrics_summary) instead of needing in-DAX decade-bucketing logic."""
    df = entry_rate.copy()
    df["decade"] = (df["year"] // 10 * 10).astype(str) + "s"
    df = df[df["decade"].isin(DECADE_ORDER)]
    out = df.groupby("decade")["new_top10_artists"].mean().round(2).rename(
        "avg_new_top10_artists_per_year").reset_index()
    return out


def incumbency_persistence(hot100):
    """% of this week's Top 10 performers who were also in last week's Top 10,
    averaged per decade. Only compares adjacent chart dates that are actually
    consecutive weeks (7 days apart) to avoid bridging real archive gaps."""
    top10 = hot100[hot100["rank"] <= 10][["chart_date", "decade", "performer"]].copy()
    dates = sorted(top10["chart_date"].unique())
    by_date = {d: set(top10.loc[top10["chart_date"] == d, "performer"]) for d in dates}

    records = []
    for i in range(1, len(dates)):
        prev_d, curr_d = dates[i - 1], dates[i]
        if (curr_d - prev_d) != pd.Timedelta(days=7):
            continue  # skip archive gaps / irregular weeks
        curr_set = by_date[curr_d]
        prev_set = by_date[prev_d]
        if not curr_set:
            continue
        persistence = len(curr_set & prev_set) / len(curr_set)
        decade = top10.loc[top10["chart_date"] == curr_d, "decade"].iloc[0]
        records.append({"chart_date": curr_d, "decade": decade, "persistence": persistence})

    weekly = pd.DataFrame(records)
    summary = weekly.groupby("decade")["persistence"].mean().round(4).rename(
        "avg_incumbency_persistence").reset_index()
    return summary


def album_sales_concentration():
    df = pd.read_csv(CSV_DIR / "album_sales_top50_by_decade.csv")
    rows = []
    for decade, g in df.groupby("decade"):
        g = g.sort_values("rank_in_decade")
        total50 = g["sales"].sum()
        top10 = g.iloc[:10]["sales"].sum()
        top25 = g.iloc[:25]["sales"].sum()
        rows.append({
            "decade": decade,
            "top50_total_sales": int(total50),
            "top10_share_of_top50": round(top10 / total50, 4),
            "top25_share_of_top50": round(top25 / total50, 4),
        })
    out = pd.DataFrame(rows)
    out["decade"] = pd.Categorical(out["decade"], categories=DECADE_ORDER, ordered=True)
    return out.sort_values("decade").reset_index(drop=True)


def main():
    print("Loading Hot 100 archive...")
    hot100_all = pd.read_csv(CSV_DIR / "hot100_full_1958_present.csv", parse_dates=["chart_date"])
    hot100 = hot100_all[hot100_all["decade"].isin(DECADE_ORDER)].copy()

    print("Computing chart-share concentration (HHI, top-10%/top-1%)...")
    concentration, artist_summary = chart_share_concentration(hot100)

    print("Computing #1 longevity...")
    longevity = number_one_longevity(hot100)

    print("Computing new-artist entry rate (turnover)...")
    entry_rate = new_artist_entry_rate(hot100_all)
    turnover_decade = turnover_by_decade(entry_rate)

    print("Computing incumbency persistence...")
    persistence = incumbency_persistence(hot100)

    print("Computing album sales concentration...")
    album_conc = album_sales_concentration()

    summary = concentration.merge(longevity, on="decade").merge(turnover_decade, on="decade").merge(
        persistence, on="decade").merge(album_conc, on="decade")
    summary["decade"] = pd.Categorical(summary["decade"], categories=DECADE_ORDER, ordered=True)
    summary = summary.sort_values("decade").reset_index(drop=True)

    summary.to_csv(CSV_DIR / "decade_metrics_summary.csv", index=False)
    artist_summary.to_csv(CSV_DIR / "artist_decade_hot100_summary.csv", index=False)
    entry_rate.to_csv(CSV_DIR / "new_artist_entries_by_year.csv", index=False)

    print("\n=== decade_metrics_summary.csv ===")
    print(summary.to_string(index=False))
    print(f"\nWrote: {CSV_DIR / 'decade_metrics_summary.csv'}")
    print(f"Wrote: {CSV_DIR / 'artist_decade_hot100_summary.csv'} ({len(artist_summary):,} rows)")
    print(f"Wrote: {CSV_DIR / 'new_artist_entries_by_year.csv'} ({len(entry_rate):,} rows)")


if __name__ == "__main__":
    main()
