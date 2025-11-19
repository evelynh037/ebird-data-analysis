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
        st.error(f"拉取全美观测失败：{res.status_code} {res.text}")
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
        st.error(f"缺少必要字段: {needed_cols - set(all_df.columns)}")
        return None

    # 处理时间
    all_df = all_df.copy()
    all_df["obsDt"] = pd.to_datetime(all_df["obsDt"], errors="coerce")
    all_df = all_df.dropna(subset=["obsDt", "lat", "lng"])

    if all_df.empty:
        st.warning("该鸟类在最近 30 天全美无有效观测记录")
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
        观测地点：{r.get('locName', '未知')}<br>
        数量：{r.get('howMany', 'N/A')}<br>
        日期：{r['obsDt'].strftime('%Y-%m-%d')}
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

st.title("🦅 eBird 观鸟查询 + 照片 + 全美热力图")

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
    st.subheader("① 按地区获取最新观测列表")

    region = st.text_input("输入地区代码 (如 US-IL, 默认 US-IL)", "US-IL")

    if st.button("获取观鸟数据"):
        df_region = fetch_ebird_data(region)
        st.session_state["region_df"] = df_region  # 存起来
        if df_region.empty:
            st.warning("没有获取到数据")
        else:
            st.success(f"成功获取 {len(df_region)} 条记录")

    if not st.session_state["region_df"].empty:
        st.dataframe(st.session_state["region_df"].head())

    st.markdown("---")
    st.subheader("② 搜索鸟类并显示照片 + 生成热力图")

    user_bird = st.text_input("输入鸟名（支持模糊匹配，如 sparrow、robin 等）")

    if st.button("搜索 & 生成热力图"):
        # 优先用已经拉过的地区 df，没有就再拉一次
        df = st.session_state["region_df"]
        if df.empty:
            df = fetch_ebird_data(region)
            st.session_state["region_df"] = df

        if df.empty:
            st.warning("数据为空，请先确保地区有观测记录")
        else:
            best = find_best_match(df, user_bird)

            if not best:
                st.error("没有找到匹配鸟名")
            else:
                st.success(f"最近似匹配：**{best}**")

                row = df[df["comName"] == best].iloc[0]
                taxon_code = row.get("taxonCode") or row.get("speciesCode")

                if not taxon_code:
                    st.error("该鸟类没有 taxonCode，无法抓取照片 / 热力图")
                else:
                    # 照片
                    img_url = fetch_bird_photo(taxon_code)
                    if img_url:
                        st.image(img_url, caption=best, use_container_width=True)
                    else:
                        st.write(f"📷去 eBird 看看： https://ebird.org/species/{taxon_code}")

                    st.write("### 📝 当前地区的一条观测记录")
                    st.json(row.to_dict())

                    # 全美 30 天观测，存到 session_state，用于右边热力图
                    all_df = fetch_us_recent_for_species(taxon_code)
                    st.session_state["heatmap_df"] = all_df
                    st.session_state["heatmap_bird_name"] = best


# ---------- 右边：全美最近 30 天热力图 ----------
with col2:
    st.subheader("③ 全美最近 30 天观测热力图")

    if (
        st.session_state["heatmap_df"] is None
        or st.session_state["heatmap_df"].empty
        or st.session_state["heatmap_bird_name"] is None
    ):
        st.info("👉 先搜索鸟名，生成热力图数据。")
    else:
        all_df = st.session_state["heatmap_df"]
        bird_name = st.session_state["heatmap_bird_name"]

        st.markdown(f"**当前鸟种：{bird_name}**  （最近 30 天，全美）")

        folium_map = build_heatmap(all_df)
        if folium_map is not None:
            st_data = st_folium(folium_map, width=800, height=550)




# =========================================================
# =============== ④ 未来热点城市预测 + 迁徙方向分析 ===============
# =========================================================

import numpy as np

st.write("---")
st.subheader("④ 未来 7 天可能出现的城市 + 迁徙方向分析")

# 必须已有热力图数据
if (
    "heatmap_df" in st.session_state
    and isinstance(st.session_state["heatmap_df"], pd.DataFrame)
    and not st.session_state["heatmap_df"].empty
):

    df_pred = st.session_state["heatmap_df"].copy()
    df_pred["obsDt"] = pd.to_datetime(df_pred["obsDt"], errors="coerce")
    df_pred = df_pred.dropna(subset=["obsDt", "lat", "lng", "locName"])
    df_pred = df_pred.sort_values("obsDt")

    # ======================
    # ① 未来 7 天热点城市预测
    # ======================
    st.markdown("### 🌆 未来 7 天：最可能观测到该鸟的城市（基于最近 30 天）")

    if df_pred.empty:
        st.warning("数据不足，无法预测未来城市")
    else:
        # 统计 locName 出现次数（频率越高越可能再次观测到）
        top_cities = (
            df_pred["locName"]
            .value_counts()
            .reset_index()
            .rename(columns={"index": "city", "locName": "count"})
        )

        top_cities["probability"] = top_cities["count"] / top_cities["count"].sum()

        st.write("📍 **未来最可能出现的前 5 个城市**（按过去 30 天频率预测）")
        st.dataframe(top_cities.head(5))

        # 给用户解释
        st.info(
            "⚠️ 说明：未来 7 天预测基于过去 30 天谁出现得最频繁；"
            "实际迁徙行为可能受天气、季节和个体差异影响。"
        )

    # ======================
    # ② 迁徙方向分析（北/南/不动）
    # ======================
    st.markdown("### 🧭 最近 30 天迁徙方向判断")

    if len(df_pred) < 3:
        st.warning("观测点太少，无法分析方向")
    else:
        # 按时间计算纬度变化速度
        df_pred = df_pred.sort_values("obsDt")
        df_pred["lat_shift"] = df_pred["lat"].diff()
        df_pred["day_shift"] = df_pred["obsDt"].diff().dt.total_seconds() / (3600 * 24)

        df_pred = df_pred.dropna(subset=["lat_shift", "day_shift"])

        # 平均每天纬度变化
        df_pred["lat_per_day"] = df_pred["lat_shift"] / df_pred["day_shift"]
        mean_lat_change = df_pred["lat_per_day"].mean()

        # 判断方向
        if mean_lat_change > 0.1:
            direction = "⬆️ **从南向北迁徙（明显北移）**"
        elif mean_lat_change < -0.1:
            direction = "⬇️ **从北向南迁徙（明显南移）**"
        else:
            direction = "➡️ **无明显方向，基本保持在同一纬度活动**"

        st.success(direction)
        st.write(f"（平均每天纬度变化：{mean_lat_change:.4f}°）")

else:
    st.info("👉 请先在左侧搜索鸟类以生成 热力图数据，再查看迁徙趋势与预测。")
