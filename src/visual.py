import folium
import pandas as pd
import os
from matplotlib import cm, colors
from folium import IFrame, Popup
import sqlite3
import json


def generate_species_map(DB_PATH):
    """
    Generate an HTML map with:
      - Hotspot Count (log) choropleth
      - Species Richness (log) choropleth
      - Per-species point layers (clickable popups linking to AllAboutBirds)
      - Layer control + JS to enforce only one species layer visible at once
    Saves to: /opt/airflow/src/docs/index.html
    """

    # ----------------------------
    # 1) DB: read required tables
    # ----------------------------
    conn = sqlite3.connect(DB_PATH)

    # notable birds (code -> common name)
    notable_birds_df = pd.read_sql("SELECT speciesCode, comName FROM notable_birds", conn)

    # state reference (state_id -> state_code)
    state_ref = pd.read_sql("SELECT state_id, state_code FROM states", conn)

    # state hotspot stats table (expects columns at least: state_id, hotspot_count, species_richness, and optionally log_* versions)
    state_stats = pd.read_sql("SELECT * FROM state_hotspot_stats", conn)

    # Ensure numeric log columns exist; if not, compute safe log1p versions
    if "log_hotspot" not in state_stats.columns and "hotspot_count" in state_stats.columns:
        state_stats["log_hotspot"] = (state_stats["hotspot_count"].fillna(0).astype(float) + 1).apply(np.log)
    if "log_richness" not in state_stats.columns and "species_richness" in state_stats.columns:
        state_stats["log_richness"] = (state_stats["species_richness"].fillna(0).astype(float) + 1).apply(np.log)

    # merge state_code into stats
    state_stats = state_stats.merge(state_ref, on="state_id", how="left")

    # ----------------------------
    # 2) state_code -> FIPS mapping
    # ----------------------------
    state_fips = {
        'AL':'01','AK':'02','AZ':'04','AR':'05','CA':'06',
        'CO':'08','CT':'09','DE':'10','FL':'12','GA':'13',
        'HI':'15','ID':'16','IL':'17','IN':'18','IA':'19',
        'KS':'20','KY':'21','LA':'22','ME':'23','MD':'24',
        'MA':'25','MI':'26','MN':'27','MS':'28','MO':'29',
        'MT':'30','NE':'31','NV':'32','NH':'33','NJ':'34',
        'NM':'35','NY':'36','NC':'37','ND':'38','OH':'39',
        'OK':'40','OR':'41','PA':'42','RI':'44','SC':'45',
        'SD':'46','TN':'47','TX':'48','UT':'49','VT':'50',
        'VA':'51','WA':'53','WV':'54','WI':'55','WY':'56'
    }
    state_stats["fips"] = state_stats["state_code"].map(state_fips).astype(str)

    # ----------------------------
    # 3) Load GeoJSON (ensure feature.id = FIPS)
    # ----------------------------
    GEOJSON_PATH = "/opt/airflow/src/shp/us-states.json"
    with open(GEOJSON_PATH, "r") as f:
        us_geo = json.load(f)

    # set feature.id to STATEFP (if present) to match our "fips" strings
    for feature in us_geo.get("features", []):
        props = feature.get("properties", {})
        if "STATEFP" in props:
            feature["id"] = str(props["STATEFP"]).zfill(2)
        elif "STATE" in props:
            # fallback if different property name is used
            feature["id"] = str(props["STATE"])
        # else leave id as-is (hope it already matches)

    # ----------------------------
    # 4) Load species tables from DB (joined with notable birds to get names)
    # ----------------------------
    species_files = {}
    # iterate over (code, common name)
    for code, common_name in list(notable_birds_df.itertuples(index=False, name=None)):
        table = f"species_{code}"
        try:
            query = f"""
                SELECT s.*, n.comName AS comName, n.sciName AS sciName
                FROM {table} AS s
                JOIN notable_birds AS n ON s.speciesCode = n.speciesCode
            """
            df = pd.read_sql(query, conn)
            if not df.empty:
                species_files[common_name] = df
        except Exception:
            # table may not exist — skip quietly
            continue

    conn.close()

    # ----------------------------
    # 5) Color palette for species (bright colors)
    # ----------------------------
    num_species = max(1, len(species_files))
    cmap = cm.get_cmap("tab20c", num_species)  # brighter set
    species_colors = {name: colors.to_hex(cmap(i)) for i, name in enumerate(species_files.keys())}

    # ----------------------------
    # 6) Build map
    # ----------------------------
    m = folium.Map(location=[39.8283, -98.5795], zoom_start=5)

    # Hotspot Count (log) choropleth, no checkbox
    folium.Choropleth(
        geo_data=us_geo,
        data=state_stats,
        columns=["fips", "log_hotspot"],
        key_on="feature.id",
        fill_color="OrRd",
        fill_opacity=0.3,
        line_opacity=0.2,
        name="Hotspot density",
        legend_name="Hotspot Count (log)",
        show = False
    ).add_to(m)
    

    # Species Richness (log) choropleth, same approach
    folium.Choropleth(
        geo_data=us_geo,
        data=state_stats,
        columns=["fips", "log_richness"],
        key_on="feature.id",
        fill_color="YlGnBu",
        name="Species Richness",
        fill_opacity=0.3,
        line_opacity=0.2,
        legend_name="Species Richness (log)"
    ).add_to(m)

    # ----------------------------
    # 7) Per-species point layers
    # ----------------------------
    for species_name, df in species_files.items():
        fg = folium.FeatureGroup(name=species_name, show=False)
        for _, row in df.iterrows():
            lat = row.get("LATITUDE") or row.get("lat")
            lon = row.get("LONGITUDE") or row.get("lng")
            if pd.isna(lat) or pd.isna(lon):
                continue

            url_name = species_name.replace(" ", "_")
            link = f"https://www.allaboutbirds.org/guide/{url_name}/overview"
            species_html = f'<a href="{link}" target="_blank"><b>{species_name}</b></a>'

            popup_html = (
                species_html + "<br>"
                f"<i>{row.get('sciName', '')}</i><br>"
                f"Location: {row.get('locName', row.get('LOCATION NAME', ''))}<br>"
                f"Count: {row.get('howMany', row.get('OBSERVATION COUNT', ''))}<br>"
                f"Date: {row.get('obsDt', row.get('OBSERVATION DATE', ''))}"
            )

            iframe = IFrame(html=popup_html, width=260, height=140)
            popup = Popup(iframe, max_width=260)

            folium.CircleMarker(
                location=[lat, lon],
                radius=5,
                color=species_colors.get(species_name, "black"),
                fill=True,
                fill_opacity=0.9,
                popup=popup
            ).add_to(fg)

        fg.add_to(m)

    # ----------------------------
    # 8) Layer control + JS to allow only one species layer at once
    # ----------------------------
    folium.LayerControl(collapsed=False).add_to(m)

    js = """
    <script>
    document.addEventListener('DOMContentLoaded', function() {
        function isSpecies(label){
            return !label.includes("Richness") && !label.includes("Hotspot");
        }
        var checkboxes = document.querySelectorAll('.leaflet-control-layers-selector[type="checkbox"]');
        checkboxes.forEach(function(cb){
            cb.addEventListener('change', function(){
                let label = this.nextSibling.textContent.trim();
                if (this.checked && isSpecies(label)){
                    checkboxes.forEach(function(other){
                        let otherLabel = other.nextSibling.textContent.trim();
                        if (other !== cb && other.checked && isSpecies(otherLabel)){
                            other.click();
                        }
                    });
                }
            });
        });
    });
    </script>
    """

    # ----------------------------
    # 9) Save output HTML
    # ----------------------------
    output_dir = "/opt/airflow/src/docs"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "index.html")
    m.save(output_path)
    with open(output_path, "a") as f:
        f.write(js)

    print(f"✓ Map saved to: {output_path}")