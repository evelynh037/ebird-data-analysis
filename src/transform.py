import geopandas as gpd
from shapely.geometry import Point
import pandas as pd
import numpy as np


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

def transform_hotspot_stats(df_hot, state_df):
    # extract state two-letter code (e.g., "US-CA" → "CA")
    df_hot["state_code"] = df_hot["subnational1Code"].str.split("-").str[1]

    # aggregate hotspot count per state
    hotspot_count = (
        df_hot.groupby("state_code", as_index=False)
        .size()
        .rename(columns={"size": "hotspot_count"})
    )

    # compute species richness per state (max numSpeciesAllTime within state)
    species_richness = (
        df_hot.groupby("state_code", as_index=False)["numSpeciesAllTime"]
        .max()
        .rename(columns={"numSpeciesAllTime": "species_richness"})
    )

    # merge hotspot stats into one table
    state_stats = hotspot_count.merge(species_richness, on="state_code")

    # map state_code → state_id 
    state_stats = state_stats.merge(state_df, on="state_code", how="left")

    # replace 'state_code' with 'state_id'
    state_stats = state_stats[["state_id", "hotspot_count", "species_richness"]]
    
    # apply log transform (log1p avoids log(0))
    state_stats["log_hotspot"] = np.log1p(state_stats["hotspot_count"])
    state_stats["log_richness"] = np.log1p(state_stats["species_richness"])

    # keep only logged columns
    state_stats = state_stats[["state_id", "log_hotspot", "log_richness"]]

    # sort by richness log
    state_stats = state_stats.sort_values("log_richness", ascending=False)

    return state_stats