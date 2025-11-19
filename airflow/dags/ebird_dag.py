import sys
import os
sys.path.append("/opt/airflow/src")

from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
import pandas as pd
import geopandas as gpd

from get_data import fetch_notable_birds, fetch_species_observations, fetch_hotspots
from transform import transform_notice_birds, transform_observations, transform_hotspot_stats
from load import load_notable_birds_to_sqlite, load_species_observations_to_sqlite, load_states_to_sqlite, load_state_hotspot_stats
from visual import generate_species_map

# ---- DAG arguments ----
default_args = {
    "owner": "ebird_project",
    "depends_on_past": False,
    "start_date": datetime(2025, 11, 18),
}

dag = DAG(
    dag_id="ebird_etl",
    default_args=default_args,
    schedule_interval="@daily",
    catchup=False,
    tags=["ebird", "etl"]
)

# ---- Task functions ----
notable_REGION = "US-UT"
observe_REGION = "US"
hotspot_REGION = "US"
API_KEY = os.environ.get("EBIRD_API_KEY")
if not API_KEY:
    raise ValueError("EBIRD_API_KEY environment variable is not set")
DB_PATH = "/opt/airflow/src/db/ebird.db"

def extract_task(**kwargs):
    notable_df = fetch_notable_birds(notable_REGION, API_KEY)
    top_species = transform_notice_birds(notable_df, scale=10)
    species_codes = top_species["speciesCode"].tolist()
    species_obs = fetch_species_observations(species_codes, observe_REGION, API_KEY)
    hotspots = fetch_hotspots(hotspot_REGION, API_KEY)
    
    return {
        "top_species": top_species.to_dict(),
        "species_obs": {k: v.to_dict() for k, v in species_obs.items()},
        "hotspots": hotspots.to_dict()
    }

def transform_task(ti, **kwargs):
    data = ti.xcom_pull(task_ids="extract")
    species_obs = {k: pd.DataFrame(v) for k, v in data["species_obs"].items()}
    df_hot = pd.DataFrame(data["hotspots"])

    # path inside Docker
    us_states = gpd.read_file("/opt/airflow/src/shp/cb_2018_us_state_20m.shp")
    states_df, transformed_species = transform_observations(species_obs, us_states)
    
    transformed_hotshpot = transform_hotspot_stats(df_hot, states_df)
    return {
        "states_df": states_df.to_dict(),
        "transformed_species": {k: v.to_dict() for k, v in transformed_species.items()},
        "transformed_hotspot": transformed_hotshpot.to_dict()
    }

def load_task(ti, **kwargs):
    data = ti.xcom_pull(task_ids="transform")
    top = ti.xcom_pull(task_ids="extract")
    
    states_df = pd.DataFrame(data["states_df"])
    top_species = pd.DataFrame(top["top_species"])
    transformed_species = {k: pd.DataFrame(v) for k, v in data["transformed_species"].items()}
    transform_hotspot_stats = pd.DataFrame(data["transformed_hotspot"])
    
    load_states_to_sqlite(states_df)
    load_species_observations_to_sqlite(transformed_species)
    load_notable_birds_to_sqlite(top_species)
    load_state_hotspot_stats(transform_hotspot_stats)

def visualize_task(**kwargs):
    generate_species_map(DB_PATH)
    
    
extract = PythonOperator(
    task_id="extract",
    python_callable=extract_task,
    dag=dag
)

transform = PythonOperator(
    task_id="transform",
    python_callable=transform_task,
    dag=dag
)

load = PythonOperator(
    task_id="load",
    python_callable=load_task,
    dag=dag
)

visualize = PythonOperator(
    task_id="visualize",
    python_callable=visualize_task,
    dag=dag
)

extract >> transform >> load >> visualize