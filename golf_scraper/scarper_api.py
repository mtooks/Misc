#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GolfV2 utilisation analysis with JSON caching, day-of-week stats,
and seasonality charts.
"""

import json, urllib.parse
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
import pandas as pd
import matplotlib.pyplot as plt

# ─────────── USER-CONFIGURABLE CONSTANTS ───────────────────────────────────
BASE_URL   = "https://golfv2.marianatek.com/api/customer/v1/classes"
REGION_ID  = 48541
DATE_FROM  = "2022-06-09"
DATE_TO    = "2025-04-29"

OUTDIR     = Path("output")          # CSVs + PNGs end up here
CACHEDIR   = Path("cache")           # raw JSON is cached here
EASTERN    = ZoneInfo("America/New_York")

# If the endpoint needs auth:
# HEADERS = {"Cookie": "..."}
HEADERS = {}
# ────────────────────────────────────────────────────────────────────────────


def cache_get(url: str, params=None) -> dict:
    """
    GET a URL and cache the JSON payload in CACHEDIR using a deterministic
    file name.  If the file already exists, load it from disk instead.
    """
    CACHEDIR.mkdir(parents=True, exist_ok=True)
    key = url
    if params:
        key += "?" + urllib.parse.urlencode(sorted(params.items()))
    fname = CACHEDIR / (urllib.parse.quote_plus(key) + ".json")

    if fname.exists():
        with fname.open() as f:
            return json.load(f)

    r = requests.get(url, params=params, headers=HEADERS, timeout=90)
    r.raise_for_status()
    data = r.json()
    with fname.open("w") as f:
        json.dump(data, f)
    return data


def fetch_range(start: str, end: str, region: int = REGION_ID) -> pd.DataFrame:
    """Return a DataFrame of bookings between two ISO yyyy-mm-dd dates."""
    params = {
        "min_start_date": start,
        "max_start_date": end,
        "page_size": 500,
        "region": region,
        "format": "json",
    }

    url, rows = BASE_URL, []
    while url:
        j = cache_get(url, params=params)
        rows.extend(j["results"])

        url = j["next"]
        if url and not url.startswith("http"):
            url = urllib.parse.urljoin(BASE_URL, url)
        params = None                  # only on first request

    df = pd.json_normalize(rows)
    df["start_dt_utc"] = pd.to_datetime(df["start_datetime"], utc=True)
    df["start_dt"]     = df["start_dt_utc"].dt.tz_convert(EASTERN)
    df["bays_booked"]  = df["capacity"] - df["available_spot_count"]
    df["util"]         = df["bays_booked"] / df["capacity"]
    df = df.rename(columns={"location.name": "location"})
    keep = ["id", "location", "capacity", "bays_booked", "util", "start_dt"]
    return df[keep]


def classify_season(ts: pd.Timestamp) -> str:
    """Return 'Winter', 'Spring', 'Summer', or 'Fall' for an Eastern-time ts."""
    month = ts.month
    if   month in (12, 1, 2):
        return "Winter"
    elif month in (3, 4, 5):
        return "Spring"
    elif month in (6, 7, 8):
        return "Summer"
    else:
        return "Fall"


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)

    df = fetch_range(DATE_FROM, DATE_TO)

    # ── 1 hour-level CSV ───────────────────────────────────────────────────
    df_hour = (df.groupby(["location", "start_dt"])
                 .agg(bay_hours_offered=("capacity", "sum"),
                      bay_hours_sold   =("bays_booked", "sum"))
                 .reset_index())
    df_hour["utilisation"] = df_hour["bay_hours_sold"] / df_hour["bay_hours_offered"]
    df_hour.to_csv(OUTDIR / "utilization_by_hour.csv", index=False)

    # ── 2 daily CSV with day-of-week info ──────────────────────────────────
    df_hour["date_local"]   = df_hour["start_dt"].dt.date
    df_hour["dow"]          = df_hour["start_dt"].dt.day_name()
    df_day = (df_hour.groupby(["location", "date_local", "dow"])
                        .agg(hours_offered=("bay_hours_offered", "sum"),
                             hours_sold   =("bay_hours_sold",   "sum"))
                        .reset_index())
    df_day["utilisation"] = df_day["hours_sold"] / df_day["hours_offered"]
    df_day.to_csv(OUTDIR / "daily_utilization_summary.csv", index=False)

    # ── 3 average by day of week ───────────────────────────────────────────
    dow_avg = (df_day.groupby(["location", "dow"])
                      .agg(avg_utilisation=("utilisation", "mean"))
                      .reset_index())
    # ensure Mon-Sun order
    dow_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    dow_avg["dow"] = pd.Categorical(dow_avg["dow"], categories=dow_order, ordered=True)
    dow_avg = dow_avg.sort_values(["location", "dow"])
    dow_avg.to_csv(OUTDIR / "dow_utilization.csv", index=False)

    # ── 4 add season & plot seasonality per location ───────────────────────
    df_day["season"] = pd.Categorical(
        [classify_season(pd.Timestamp(d).replace(tzinfo=EASTERN)) for d in df_day["date_local"]],
        categories=["Winter","Spring","Summer","Fall"],
        ordered=True,
    )

    for loc, grp in df_day.groupby("location"):
        # line chart of daily utilisation coloured by season
        fig = plt.figure(figsize=(10, 4))
        for season, sub in grp.groupby("season"):
            plt.plot(sub["date_local"], sub["utilisation"], label=season)
        plt.title(f"{loc} – Daily Utilisation by Season")
        plt.xlabel("Date")
        plt.ylabel("Utilisation")
        plt.ylim(0, 1)
        plt.legend()
        plt.tight_layout()
        fname = OUTDIR / f"{loc.lower().replace(' ','_')}_seasonality.png"
        plt.savefig(fname, dpi=150)
        plt.close(fig)

        # bar chart of average utilisation by season
        season_avg = (grp.groupby("season")["utilisation"].mean())
        fig = plt.figure()
        season_avg.plot(kind="bar")
        plt.title(f"{loc} – Average Utilisation by Season")
        plt.ylabel("Utilisation")
        plt.ylim(0, 1)
        plt.tight_layout()
        fname = OUTDIR / f"{loc.lower().replace(' ','_')}_season_avg.png"
        plt.savefig(fname, dpi=150)
        plt.close(fig)

    print("✓ JSON cached to", CACHEDIR.resolve())
    print("✓ CSVs and PNGs written to", OUTDIR.resolve())


# ────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
