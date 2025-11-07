import requests
import pandas as pd
import os
from datetime import datetime
import folium
import matplotlib
import matplotlib.cm as cm
import matplotlib.colors as mcolors

# === 用户输入 ===
bird_name = input("请输入鸟的英文名（例如：American Robin）: ").strip()

# === 常见鸟种与 eBird species code 对照表（可扩展） ===
species_map = {
    "american robin": "amerob",
    "northern cardinal": "norcar",
    "blue jay": "blujay",
    "house sparrow": "houspa",
    "mourning dove": "moudov",
    "canada goose": "cangoo",
    "mallard": "mallar3",
    "american goldfinch": "amegfi",
    "black-capped chickadee": "bkcchi",
    "red-tailed hawk": "rethaw"
}

# === 统一小写匹配 ===
bird_key = bird_name.lower()

if bird_key not in species_map:
    print(f"❌ 暂不支持 '{bird_name}'，请手动在 species_map 添加物种代码。")
    print("💡 提示：可在 https://ebird.org/species/ 查找 species code，例如 American Robin -> amerob")
    exit()

species_code = species_map[bird_key]
print(f"✅ 识别到 {bird_name} 的物种代码为: {species_code}")

# === eBird API ===
API_TOKEN = "3g5voge8rcai"  # ⚠️ 替换成你的 eBird API key
headers = {"X-eBirdApiToken": API_TOKEN}
region_code = "US-IL"
url = f"https://api.ebird.org/v2/data/obs/{region_code}/recent/{species_code}"

print(f"🌐 正在从 eBird 获取 {bird_name} 最近 30 天的观测数据...")
res = requests.get(url, headers=headers)

if res.status_code != 200:
    print(f"⚠️ 请求失败：{res.status_code} - {res.text}")
    exit()

data = res.json()
df = pd.DataFrame(data)

if df.empty:
    print(f"❌ 没有找到 {bird_name} 最近 30 天的观测记录。")
    exit()

# === 处理时间列 ===
df["obsDt"] = pd.to_datetime(df["obsDt"], errors="coerce", format='mixed')
df = df.sort_values("obsDt")

# === 保存结果 ===
output_dir = "data/processed/subsets"
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, f"{bird_name.replace(' ', '_').lower()}_recent.csv")
df.to_csv(output_path, index=False)
print(f"✅ 已保存: {output_path}")

# === 打印轨迹摘要 ===
print(f"共 {len(df)} 条记录，涉及 {df['locName'].nunique()} 个地点。")
print(df[["locName", "lat", "lng", "obsDt"]].head())

# === 构建颜色梯度（按时间）===
# 越新的日期颜色越深
norm = mcolors.Normalize(vmin=df["obsDt"].min().timestamp(), vmax=df["obsDt"].max().timestamp())
cmap = cm.get_cmap('YlOrRd')  # 黄色→红色渐变
df["color"] = df["obsDt"].apply(lambda x: matplotlib.colors.to_hex(cmap(norm(x.timestamp()))))

# === 生成轨迹地图 ===
m = folium.Map(location=[df["lat"].mean(), df["lng"].mean()], zoom_start=6)

for _, row in df.iterrows():
    folium.CircleMarker(
        location=[row["lat"], row["lng"]],
        radius=6,
        color=row["color"],
        fill=True,
        fill_opacity=0.8,
        popup=f"{row['locName']}<br>{row['obsDt'].strftime('%Y-%m-%d %H:%M')}"
    ).add_to(m)

# 添加颜色图例
# === 生成颜色图例（修正版） ===
vmin = df["obsDt"].min().timestamp()
vmax = df["obsDt"].max().timestamp()

colormap = folium.LinearColormap(
    colors=[matplotlib.colors.to_hex(cmap(v)) for v in [0, 0.25, 0.5, 0.75, 1]],
    vmin=vmin,
    vmax=vmax,
    caption="Observation Date (浅→深 = 时间早→晚)"
)

# 让图例显示时间字符串
colormap.caption = f"观测日期范围：{df['obsDt'].min().strftime('%Y-%m-%d')} → {df['obsDt'].max().strftime('%Y-%m-%d')}"
colormap.add_to(m)


map_path = os.path.join(output_dir, f"{bird_name.replace(' ', '_').lower()}_recent_map_colored.html")
m.save(map_path)
print(f"📍 彩色时间地图已保存为: {map_path}")
