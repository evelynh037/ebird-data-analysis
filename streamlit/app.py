import streamlit as st
import pandas as pd
import requests
from difflib import get_close_matches
import folium
from streamlit_folium import st_folium
import matplotlib
import matplotlib.cm as cm
import matplotlib.colors as mcolors
import numpy as np
import re

# ======= Your eBird API Key =======
EBIRD_API_KEY = "3g5voge8rcai"


# -------------------- Fetch recent observations by region --------------------
def fetch_ebird_data(region="US-IL"):
    url = f"https://api.ebird.org/v2/data/obs/{region}/recent"
    headers = {"X-eBirdApiToken": EBIRD_API_KEY}

    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        st.error(f"Error {res.status_code}: {res.text}")
        return pd.DataFrame()

    return pd.DataFrame(res.json())


# -------------------- Fetch photos by taxonCode --------------------
def fetch_bird_photo(taxon_code: str):
    url = f"https://api.ebird.org/v2/media/catalog?taxonCode={taxon_code}&mediaType=photo"
    headers = {"X-eBirdApiToken": EBIRD_API_KEY}

    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        return None

    items = res.json()
    if not items:
        return None

    return items[0].get("mediaUrl")


# -------------------- Fetch U.S. recent 30-day records for species --------------------
def fetch_us_recent_for_species(taxon_code: str):
    url = f"https://api.ebird.org/v2/data/obs/US/recent/{taxon_code}"
    headers = {"X-eBirdApiToken": EBIRD_API_KEY}

    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        st.error(f"Failed to fetch nationwide observations: {res.status_code} {res.text}")
        return pd.DataFrame()

    return pd.DataFrame(res.json())


# -------------------- Fuzzy match bird name --------------------
def find_best_match(df: pd.DataFrame, user_input: str):
    names = df["comName"].dropna().unique().tolist()
    matches = get_close_matches(user_input, names, n=1, cutoff=0.3)
    return matches[0] if matches else None


# -------------------- Build heatmap --------------------
def build_heatmap(all_df: pd.DataFrame):
    needed_cols = {"lat", "lng", "obsDt", "comName"}
    if not needed_cols.issubset(all_df.columns):
        st.error(f"Missing required fields: {needed_cols - set(all_df.columns)}")
        return None

    all_df = all_df.copy()
    all_df["obsDt"] = pd.to_datetime(all_df["obsDt"], errors="coerce")
    all_df = all_df.dropna(subset=["obsDt", "lat", "lng"])

    if all_df.empty:
        st.warning("No valid nationwide observations for this species in the past 30 days.")
        return None

    min_ts = all_df["obsDt"].min().timestamp()
    max_ts = all_df["obsDt"].max().timestamp()
    norm = mcolors.Normalize(vmin=min_ts, vmax=max_ts)
    cmap = cm.get_cmap("YlOrRd")

    def dt_to_color(dt):
        ts = dt.timestamp()
        return matplotlib.colors.to_hex(cmap(norm(ts)))

    all_df["color"] = all_df["obsDt"].apply(dt_to_color)

    m = folium.Map(
        location=[all_df["lat"].mean(), all_df["lng"].mean()],
        zoom_start=4,
        tiles="cartodb positron",
    )

    for _, r in all_df.iterrows():
        popup = f"""
        <b>{r.get('comName', '')}</b><br>
        Location: {r.get('locName', 'Unknown')}<br>
        Count: {r.get('howMany', 'N/A')}<br>
        Date: {r['obsDt'].strftime('%Y-%m-%d')}
        """
        folium.CircleMarker(
            location=[r["lat"], r["lng"]],
            radius=5,
            color=r["color"],
            fill=True,
            fill_opacity=0.7,
            popup=popup,
        ).add_to(m)

    return m


# =========================================================
# ========================== UI ===========================
# =========================================================

st.set_page_config(page_title="eBird Bird Finder", layout="wide")
st.title("🦅 eBird Bird Search + Photos + U.S. Heatmap")

# Session state setup
if "region_df" not in st.session_state:
    st.session_state["region_df"] = pd.DataFrame()
if "heatmap_df" not in st.session_state:
    st.session_state["heatmap_df"] = pd.DataFrame()
if "heatmap_bird_name" not in st.session_state:
    st.session_state["heatmap_bird_name"] = None

col1, col2 = st.columns([1, 1.2])

# =========================================================
# =============== COLUMN 1: REGION + SEARCH ===============
# =========================================================

with col1:
    st.subheader("① Get Latest Observations by Region")

    region = st.text_input("Enter region code (e.g., US-IL, default US-IL)", "US-IL")

    if st.button("Fetch Bird Data"):
        df_region = fetch_ebird_data(region)
        st.session_state["region_df"] = df_region

        if df_region.empty:
            st.warning("No data retrieved.")
        else:
            st.success(f"Successfully retrieved {len(df_region)} records.")

    if not st.session_state["region_df"].empty:
        st.dataframe(st.session_state["region_df"].head())

    st.markdown("---")
    st.subheader("② Search Bird, Show Photo & Generate Heatmap")

    user_bird = st.text_input("Enter bird name (fuzzy match supported, e.g., sparrow, robin)")

    if st.button("Search & Generate Heatmap"):
        df = st.session_state["region_df"]
        if df.empty:
            df = fetch_ebird_data(region)
            st.session_state["region_df"] = df

        if df.empty:
            st.warning("The dataset is empty. Please ensure the selected region has observation records.")
        else:
            best = find_best_match(df, user_bird)
            if not best:
                st.error("No matching bird name found.")
            else:
                st.success(f"Closest match: **{best}**")

                row = df[df["comName"] == best].iloc[0]
                taxon_code = row.get("taxonCode") or row.get("speciesCode")

                if not taxon_code:
                    st.error("This species has no taxonCode. Photos and heatmaps cannot be retrieved.")
                else:
                    img_url = fetch_bird_photo(taxon_code)
                    if img_url:
                        st.image(img_url, caption=best, use_container_width=True)
                    else:
                        st.write(f"📷 View on eBird: https://ebird.org/species/{taxon_code}")

                    st.write("### 📝 A Sample Observation Record from This Region")
                    st.json(row.to_dict())

                    all_df = fetch_us_recent_for_species(taxon_code)
                    st.session_state["heatmap_df"] = all_df
                    st.session_state["heatmap_bird_name"] = best


# =========================================================
# ================= COLUMN 2: HEATMAP =====================
# =========================================================

with col2:
    st.subheader("③ U.S. 30-Day Observation Heatmap")

    if (
        st.session_state["heatmap_df"] is None
        or st.session_state["heatmap_df"].empty
        or st.session_state["heatmap_bird_name"] is None
    ):
        st.info("👉 Please search for a bird first to generate the heatmap.")
    else:
        all_df = st.session_state["heatmap_df"]
        bird_name = st.session_state["heatmap_bird_name"]

        st.markdown(f"**Current Species: {bird_name}** (Past 30 Days, U.S.)")

        folium_map = build_heatmap(all_df)
        if folium_map:
            st_folium(folium_map, width=800, height=550)

# =========================================================
# =============== ④ HOTSPOT + MIGRATION ===================
# =========================================================

st.write("---")
st.subheader("④ Hotspot Prediction (Next 7 Days) + Migration Direction")

# =========================================================
# Helper: Clean private / invalid locations
# =========================================================
import re

def clean_loc(loc):
    """Remove private locations like backyard / home / feeder / yard.
       Return None to drop the record.
    """
    if not isinstance(loc, str):
        return None

    text = loc.lower().strip()

    bad_words = [
        "yard", "my yard", "front yard", "back yard",
        "backyard", "frontyard",
        "my home", "home", "my house", "house",
        "feeder", "bird feeder", "patio", "garden",
        "private residence", "private", "residence"
    ]

    for bad in bad_words:
        if bad in text:
            return None

    return loc   # keep original location


# =========================================================
# Ensure nationwide dataset exists
# =========================================================
if (
    "heatmap_df" in st.session_state
    and isinstance(st.session_state["heatmap_df"], pd.DataFrame)
    and not st.session_state["heatmap_df"].empty
):

    df_pred = st.session_state["heatmap_df"].copy()

    # Clean time + required fields
    df_pred["obsDt"] = pd.to_datetime(df_pred["obsDt"], errors="coerce")
    df_pred = df_pred.dropna(subset=["obsDt", "lat", "lng", "locName"])
    df_pred = df_pred.sort_values("obsDt")

    # Apply private location filtering
    df_pred["loc_clean"] = df_pred["locName"].apply(clean_loc)
    df_pred = df_pred.dropna(subset=["loc_clean"])

    # If after filtering all removed
    if df_pred.empty:
        st.warning("All locations were filtered out (private locations removed).")
    else:

        # =====================================================
        # ============= ① HOTSPOT CITY PREDICTION =============
        # =====================================================

        st.markdown("### 🌆 Hotspot Prediction for the Next 7 Days (Based on Past 30 Days)")

        vc = df_pred["loc_clean"].value_counts()

        top_cities = pd.DataFrame({
            "city": vc.index,
            "count": vc.values
        })

        # ensure numeric
        top_cities["count"] = pd.to_numeric(top_cities["count"], errors="coerce").fillna(0).astype(int)

        total = top_cities["count"].sum()
        top_cities["probability"] = (top_cities["count"] / total) if total > 0 else 0.0

        st.write("📍 **Top 5 Most Likely Cities (Based on the Past 30 Days)**")
        st.dataframe(top_cities.head(5))

        st.info(
            "Private locations such as home/backyard/feeder were removed. "
            "Predictions are based on public observation hotspots."
        )

        # =====================================================
        # ============= ② STATE-BASED MIGRATION ===============
        # =====================================================

        st.markdown("### 🧭 Migration Direction (State-Level, Past 30 Days)")

        if len(df_pred) < 3:
            st.warning("Not enough observations to analyze migration direction.")
        else:

            # Extract 2-letter state code (e.g., IL)
            def extract_state(loc):
                parts = str(loc).split(",")
                if len(parts) >= 2:
                    code = parts[-1].strip()
                    return code if len(code) == 2 else None
                return None

            df_pred["state"] = df_pred["loc_clean"].apply(extract_state)
            df_pred = df_pred.dropna(subset=["state"])

            if df_pred.empty:
                st.warning("No valid state information found after cleaning.")
            else:
                # avg latitude per state
                state_lat = df_pred.groupby("state")["lat"].mean().to_dict()

                earliest_state = df_pred.iloc[0]["state"]
                latest_state = df_pred.iloc[-1]["state"]

                if earliest_state in state_lat and latest_state in state_lat:
                    start_lat = state_lat[earliest_state]
                    end_lat = state_lat[latest_state]
                    lat_change = end_lat - start_lat

                    if lat_change > 1.0:
                        direction = f"⬆️ Northbound migration: {earliest_state} → {latest_state}"
                    elif lat_change < -1.0:
                        direction = f"⬇️ Southbound migration: {earliest_state} → {latest_state}"
                    else:
                        direction = f"➡️ Minimal movement: {earliest_state} → {latest_state}"

                    st.success(direction)
                    st.write(f"Latitude change: {lat_change:.2f}°")
                else:
                    st.warning("Unable to determine migration direction.")

else:
    st.info("👉 Please search for a bird first to generate nationwide data for prediction.")

