import streamlit as st
import pandas as pd
import requests
from difflib import get_close_matches
import folium
from streamlit_folium import st_folium
import matplotlib
import matplotlib.cm as cm
import matplotlib.colors as mcolors

# ========= 你的 eBird API Key =========
EBIRD_API_KEY = "3g5voge8rcai"   


# -------------------- 最近观测（按地区） --------------------
def fetch_ebird_data(region="US-IL"):
    url = f"https://api.ebird.org/v2/data/obs/{region}/recent"
    headers = {"X-eBirdApiToken": EBIRD_API_KEY}

    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        st.error(f"Error {res.status_code}: {res.text}")
        return pd.DataFrame()

    return pd.DataFrame(res.json())


# -------------------- 媒体 API: 根据 taxonCode 抓照片 --------------------
def fetch_bird_photo(taxon_code: str):
    url = f"https://api.ebird.org/v2/media/catalog?taxonCode={taxon_code}&mediaType=photo"
    headers = {"X-eBirdApiToken": EBIRD_API_KEY}

    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        return None

    items = res.json()
    if not items:
        return None

    # 拿第一张
    return items[0].get("mediaUrl")


# -------------------- 全美最近 30 天该鸟的观测 --------------------
def fetch_us_recent_for_species(taxon_code: str):
    url = f"https://api.ebird.org/v2/data/obs/US/recent/{taxon_code}"
    headers = {"X-eBirdApiToken": EBIRD_API_KEY}

    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        st.error(f"Failure：{res.status_code} {res.text}")
        return pd.DataFrame()

    return pd.DataFrame(res.json())


# -------------------- 模糊匹配鸟名 --------------------
def find_best_match(df: pd.DataFrame, user_input: str):
    names = df["comName"].dropna().unique().tolist()
    matches = get_close_matches(user_input, names, n=1, cutoff=0.3)
    return matches[0] if matches else None


# -------------------- 根据 DataFrame 画热力图（时间渐变颜色） --------------------
def build_heatmap(all_df: pd.DataFrame):
    # 确保字段存在
    needed_cols = {"lat", "lng", "obsDt", "comName"}
    if not needed_cols.issubset(all_df.columns):
        st.error(f"Missing required fields: {needed_cols - set(all_df.columns)}")
        return None

    # 处理时间
    all_df = all_df.copy()
    all_df["obsDt"] = pd.to_datetime(all_df["obsDt"], errors="coerce")
    all_df = all_df.dropna(subset=["obsDt", "lat", "lng"])

    if all_df.empty:
        st.warning("There are no valid observations for this species across the U.S. in the past 30 days.")
        return None

    # 颜色映射：越新的日期颜色越偏红
    min_ts = all_df["obsDt"].min().timestamp()
    max_ts = all_df["obsDt"].max().timestamp()
    norm = mcolors.Normalize(vmin=min_ts, vmax=max_ts)
    cmap = cm.get_cmap("YlOrRd")

    def dt_to_color(dt):
        ts = dt.timestamp()
        return matplotlib.colors.to_hex(cmap(norm(ts)))

    all_df["color"] = all_df["obsDt"].apply(dt_to_color)

    # Folium 地图
    m = folium.Map(
        location=[all_df["lat"].mean(), all_df["lng"].mean()],
        zoom_start=4,
        tiles="cartodb positron",
    )

    for _, r in all_df.iterrows():
        popup = f"""
        <b>{r.get('comName', '')}</b><br>
        Spot：{r.get('locName', '未知')}<br>
        Count：{r.get('howMany', 'N/A')}<br>
        Date：{r['obsDt'].strftime('%Y-%m-%d')}
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

st.set_page_config(page_title="eBird 观鸟助手", layout="wide")

st.title("🦅 eBird Bird Search + Photos + U.S. Heatmap")

# 初始化 session_state，用来“记住”数据，防止按钮切换时内容消失
if "region_df" not in st.session_state:
    st.session_state["region_df"] = pd.DataFrame()
if "heatmap_df" not in st.session_state:
    st.session_state["heatmap_df"] = pd.DataFrame()
if "heatmap_bird_name" not in st.session_state:
    st.session_state["heatmap_bird_name"] = None

# ---------- 左边：设置、列表 & 搜索 ----------
col1, col2 = st.columns([1, 1.2])

with col1:
    st.subheader("① Fetch Recent Sightings by Region")

    region = st.text_input("Enter a region code (e.g., US-IL, default: US-IL)", "US-IL")

    if st.button("Fetch Bird Observation Data"):
        df_region = fetch_ebird_data(region)
        st.session_state["region_df"] = df_region  # 存起来
        if df_region.empty:
            st.warning("No data found.")
        else:
            st.success(f"Successfully fetched {len(df_region)} records.")

    if not st.session_state["region_df"].empty:
        st.dataframe(st.session_state["region_df"].head())

    st.markdown("---")
    st.subheader("② Search Species, Show Photo & Generate Heatmap")

    user_bird = st.text_input("Enter a bird name (fuzzy match supported, e.g., ‘sparrow’, ‘robin’)")

    if st.button("Search & Generate Heatmap"):
        # 优先用已经拉过的地区 df，没有就再拉一次
        df = st.session_state["region_df"]
        if df.empty:
            df = fetch_ebird_data(region)
            st.session_state["region_df"] = df

        if df.empty:
            st.warning("The dataset is empty. Please make sure the selected region has observation records.")
        else:
            best = find_best_match(df, user_bird)

            if not best:
                st.error("No matching bird name found.")
            else:
                st.success(f"Closest match：**{best}**")

                row = df[df["comName"] == best].iloc[0]
                taxon_code = row.get("taxonCode") or row.get("speciesCode")

                if not taxon_code:
                    st.error("This species has no taxonCode, so photos and heatmaps cannot be retrieved.")
                else:
                    # 照片
                    img_url = fetch_bird_photo(taxon_code)
                    if img_url:
                        st.image(img_url, caption=best, use_container_width=True)
                    else:
                        st.write(f"📷View on eBird: https://ebird.org/species/{taxon_code}")

                    st.write("### 📝 A Recent Observation from This Region")
                    st.json(row.to_dict())

                    # 全美 30 天观测，存到 session_state，用于右边热力图
                    all_df = fetch_us_recent_for_species(taxon_code)
                    st.session_state["heatmap_df"] = all_df
                    st.session_state["heatmap_bird_name"] = best


# ---------- 右边：全美最近 30 天热力图 ----------
with col2:
    st.subheader("③ Nationwide Heatmap of Observations in the Past 30 Days")

    if (
        st.session_state["heatmap_df"] is None
        or st.session_state["heatmap_df"].empty
        or st.session_state["heatmap_bird_name"] is None
    ):
        st.info("👉 Please search for a bird first to generate the heatmap data.")
    else:
        all_df = st.session_state["heatmap_df"]
        bird_name = st.session_state["heatmap_bird_name"]

        st.markdown(f"**Current Species:{bird_name}**  （Past 30 Days, U.S.）")

        folium_map = build_heatmap(all_df)
        if folium_map is not None:
            st_data = st_folium(folium_map, width=800, height=550)




# =========================================================
# =============== ④ Migration Trend & Prediction ==========
# =========================================================

import numpy as np
import re

st.write("---")
st.subheader("④ Migration Trend & Prediction (Past 30 Days → Hotspots & Direction)")

# Only execute if heatmap data exists
if (
    "heatmap_df" in st.session_state
    and isinstance(st.session_state["heatmap_df"], pd.DataFrame)
    and not st.session_state["heatmap_df"].empty
):
    df_pred = st.session_state["heatmap_df"].copy()

    # ---- Date processing ----
    df_pred["obsDt"] = pd.to_datetime(df_pred["obsDt"], errors="coerce")
    df_pred = df_pred.dropna(subset=["obsDt", "lat", "lng", "locName"])
    df_pred = df_pred.sort_values("obsDt")

    # ============================================================
    # ========== ① Next 7 Days Hotspot Prediction (Cleaned) ======
    # ============================================================

    st.markdown("### 🌆 Top Likely Hotspot Areas for the Next 7 Days")

    # ---------- Clean function (ZIP + City only) ----------
    def clean_loc_name(name: str):
        """
        Clean eBird location names:
        - Remove backyard/home/private locations
        - Extract ZIP code if present
        - Extract city name (usually second-to-last item)
        - Output format: ZIP – City
        - If no ZIP: City only
        - If no city: return main part of location
        """
        if not isinstance(name, str):
            return None

        raw = name.strip()
        name_lower = raw.lower()

        # Remove private locations
        bad_keywords = [
            "yard", "backyard", "my yard", "front yard",
            "home", "my home", "house", "my house",
            "feeder", "garden", "patio", "my place"
        ]
        for kw in bad_keywords:
            if kw in name_lower:
                return None  # drop

        # Extract ZIP code
        zip_match = re.search(r"\b\d{5}\b", raw)
        zip_code = zip_match.group() if zip_match else None

        # Extract city
        parts = [p.strip() for p in raw.split(",") if len(p.strip()) > 0]
        city = None
        if len(parts) >= 2:
            candidate = parts[-2]
            if len(candidate) > 2:
                city = candidate

        # Output rules
        if zip_code and city:
            return f"{zip_code} – {city}"

        if city:
            return city

        if zip_code:
            return zip_code

        return parts[0] if len(parts) >= 1 else raw


    if df_pred.empty:
        st.warning("Not enough data to predict hotspots.")
    else:
        # Apply cleaning logic
        df_pred["clean_loc"] = df_pred["locName"].apply(clean_loc_name)
        df_clean = df_pred.dropna(subset=["clean_loc"])

        if df_clean.empty:
            st.warning("No valid public hotspot locations after filtering.")
        else:
            vc = df_clean["clean_loc"].value_counts()

            top_areas = pd.DataFrame({
                "Area": vc.index,
                "Observations": vc.values
            })

            top_areas["Observations"] = pd.to_numeric(
                top_areas["Observations"], errors="coerce"
            ).fillna(0).astype(int)

            total_count = top_areas["Observations"].sum()
            top_areas["Probability"] = (
                top_areas["Observations"] / total_count
                if total_count > 0 else 0
            )

            st.write("📍 **Top 5 Likely Hotspot Areas (Cleaned & Filtered):**")
            st.dataframe(top_areas.head(5))

            st.info(
                "Private locations (backyard, home, feeder, etc.) have been filtered out. "
                "ZIP codes and city names are extracted when available."
            )

    # ============================================================
    # ========== ② Migration Direction (State-Based) =============
    # ============================================================

    st.markdown("### 🧭 Migration Direction Over the Past 30 Days")

    if len(df_pred) < 3:
        st.warning("Not enough data to determine migration direction.")
    else:
        # Extract US state from location string
        def extract_state(loc):
            parts = str(loc).split(",")
            if len(parts) >= 2:
                s = parts[-1].strip()
                if len(s) == 2:  # e.g., IL, WI, TX
                    return s
            return None

        df_pred["state"] = df_pred["locName"].apply(extract_state)
        df_pred = df_pred.dropna(subset=["state"])

        # Average latitude per state
        state_lat = df_pred.groupby("state")["lat"].mean().to_dict()

        # Start & end of time series
        earliest_state = df_pred.iloc[0]["state"]
        latest_state = df_pred.iloc[-1]["state"]

        if earliest_state in state_lat and latest_state in state_lat:
            start_lat = state_lat[earliest_state]
            end_lat = state_lat[latest_state]
            lat_change = end_lat - start_lat

            # Determine migration direction (>1° ≈ 111 km)
            if lat_change > 1.0:
                direction = f"⬆️ Northward Migration: {earliest_state} → {latest_state}"
            elif lat_change < -1.0:
                direction = f"⬇️ Southward Migration: {earliest_state} → {latest_state}"
            else:
                direction = f"➡️ Minimal Movement: {earliest_state} → {latest_state}"

            st.success(direction)
            st.write(f"Latitude change: {lat_change:.2f}°")
        else:
            st.warning("Unable to extract enough state information.")

else:
    st.info("👉 Please search for a species first to generate heatmap data.")
