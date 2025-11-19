import folium
import pandas as pd
import os
from matplotlib import cm, colors
from folium import IFrame, Popup
import sqlite3

def generate_species_map(DB_PATH):
    # connect to db
    conn = sqlite3.connect(DB_PATH)

    # read notable_birds table
    notable_birds_df = pd.read_sql("SELECT speciesCode, comName FROM notable_birds", conn)

    # build species observations dictionary
    species_files = {}
    for code, name in list(notable_birds_df.itertuples(index=False, name=None)):
        table_name = f"species_{code}"
        try:
            query = f"""
            SELECT s.*, n.comName, n.sciName
            FROM {table_name} AS s
            JOIN notable_birds AS n
            ON s.speciesCode = n.speciesCode
            """
            species_df = pd.read_sql(query, conn)
            if not species_df.empty:
                species_files[name] = species_df
        except Exception:
            continue

    conn.close()

    # generate colors
    num_species = len(species_files)
    cmap = cm.get_cmap("Set1", num_species)
    species_colors = {name: colors.to_hex(cmap(i)) for i, name in enumerate(species_files.keys())}

    # initialize map
    m = folium.Map(location=[39.8283, -98.5795], zoom_start=5)

    # add species layers
    for species_name, df in species_files.items():
        fg = folium.FeatureGroup(name=species_name, show=False)
        for _, row in df.iterrows():
            lat = row.get("LATITUDE") or row.get("lat")
            lon = row.get("LONGITUDE") or row.get("lng")
            if pd.isna(lat) or pd.isna(lon):
                continue

            # build All About Birds URL
            url_name = species_name.replace(" ", "_")
            link = f"https://www.allaboutbirds.org/guide/{url_name}/overview"
            species_html = f'<a href="{link}" target="_blank"><b>{species_name}</b></a>'

            # build popup HTML
            popup_html = species_html + "<br>" \
                         f"<i>{row.get('sciName', '')}</i><br>" \
                         f"Location: {row.get('locName', row.get('LOCATION NAME', ''))}<br>" \
                         f"Count: {row.get('howMany', row.get('OBSERVATION COUNT', ''))}<br>" \
                         f"Date: {row.get('obsDt', row.get('OBSERVATION DATE', ''))}"

            # IFrame ensures HTML renders correctly
            iframe = IFrame(html=popup_html, width=250, height=120)
            popup = Popup(iframe, max_width=250)

            folium.CircleMarker(
                location=[lat, lon],
                radius=5,
                color=species_colors.get(species_name, "black"),
                fill=True,
                fill_opacity=0.8,
                popup=popup
            ).add_to(fg)

        fg.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    # JS to allow only one layer
    js = """
    <script>
    document.addEventListener('DOMContentLoaded', function() {
        var checkboxes = document.querySelectorAll('.leaflet-control-layers-selector[type="checkbox"]');
        checkboxes.forEach(function(cb) {
            cb.addEventListener('change', function() {
                if (this.checked) {
                    checkboxes.forEach(function(other) {
                        if (other !== cb && other.checked) {
                            other.click();
                        }
                    });
                }
            });
        });
    });
    </script>
    """

    output_dir = "/opt/airflow/src/docs"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "index.html")
    m.save(output_path)

    with open(output_path, "a") as f:
        f.write(js)

    print(f"✅ Map saved to: {output_path}")