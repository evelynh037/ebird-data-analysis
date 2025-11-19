import geopandas as gpd
from shapely.geometry import Point
import pandas as pd


def transform_notice_birds(df, scale=10):
    # aggregate num by species
    aggregated = df.groupby("speciesCode", as_index=False).agg({
        "howMany": "sum",
        "comName": "first", 
        "sciName": "first"
    })
    
    # sort by num desc
    sorted_df = aggregated.sort_values(by="howMany", ascending=True)
    
    # take the top scale number
    top_df = sorted_df.head(scale)
    
    # keep relevant column
    selected = top_df[["speciesCode", "comName", "sciName"]]
    return selected


def transform_observations(dataframes, us_states):
    transformed = {}
    
    # Ensure CRS match for spatial join
    us_states = us_states.to_crs("EPSG:4326")
    
    # Create states_df with numeric IDs
    states_df = us_states[['STUSPS', 'NAME']].drop_duplicates().reset_index(drop=True)
    states_df = states_df.rename(columns={'STUSPS': 'state_code', 'NAME': 'state_name'})
    states_df['state_id'] = states_df.index + 1  # numeric IDs starting from 1

    for species_code, df in dataframes.items():
        if df.empty:
            continue

        # Filter for validated observation
        validated = df[df["obsValid"] == True]

        # Keep relevant columns
        selected = validated[["speciesCode", "obsDt", "howMany", "lat", "lng","locName"]].copy()

        # Convert lat/lng to geometry
        geometry = [Point(xy) for xy in zip(selected["lng"], selected["lat"])]
        gdf = gpd.GeoDataFrame(selected, geometry=geometry, crs="EPSG:4326")

        # Spatial join with states
        gdf_states = gpd.sjoin(
            gdf, 
            us_states[['STUSPS', 'NAME', 'geometry']], 
            how="left", 
            predicate="intersects"
        )
        gdf_states = gdf_states.rename(columns={'STUSPS': 'state_code', 'NAME': 'state_name'})

        # Merge with numeric state IDs
        gdf_states = gdf_states.merge(
            states_df[['state_id', 'state_code']], 
            on='state_code', 
            how='left'
        )

        # Keep only relevant columns
        final_df = gdf_states[["speciesCode", "obsDt", "howMany", "lat", "lng", "state_id","locName"]].copy()
        transformed[species_code] = final_df

    return states_df[['state_id', 'state_code']], transformed