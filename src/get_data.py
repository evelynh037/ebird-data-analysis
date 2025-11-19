import requests
import pandas as pd
from typing import List, Optional

def fetch_notable_birds(region_code: str, api_key: str, max_results: int = 200, save_path: str = None) -> pd.DataFrame:
    
    url = f"https://api.ebird.org/v2/data/obs/{region_code}/recent/notable"
    headers = {"X-eBirdApiToken": api_key}
    params = {"maxResults": max_results}

    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        raise Exception(f"Error fetching data: {response.status_code}, {response.text}")

    checklists = response.json()
    notable_birds = pd.DataFrame(checklists)

    return notable_birds

def fetch_species_observations(
    species_codes: List[str],
    region_code: str,
    api_key: str,
    max_results: int = 1000,
) -> dict:

    species_data = {}
    headers = {"X-eBirdApiToken": api_key}
    params = {"maxResults": max_results}

    for species_code in species_codes:
        url = f"https://api.ebird.org/v2/data/obs/{region_code}/recent/{species_code}"
        response = requests.get(url, headers=headers, params=params)

        if response.status_code != 200:
            print(f"Failed to fetch {species_code}: {response.status_code}")
            continue

        checklists = response.json()
        print(f"Fetched {len(checklists)} checklists for {species_code}")

        if not checklists:
            continue

        df = pd.DataFrame(checklists)
        species_data[species_code] = df
        
    return species_data

def fetch_hotspots(region_code: str, api_key: str, back: int = 30, save_path: str = None) -> pd.DataFrame:
    url = f"https://api.ebird.org/v2/ref/hotspot/{region_code}"
    headers = {"X-eBirdApiToken": api_key}
    params = {"back": back, "fmt": "json"}

    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        raise Exception(
            f"Error fetching hotspots: {response.status_code}, {response.text}"
        )

    hotspots = response.json()
    hotspots_df = pd.DataFrame(hotspots)

    return hotspots_df