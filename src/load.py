import pandas as pd
import sqlite3
from typing import Dict
import os

# set relative path for the database
DB_DIR = os.path.join("src", "db")
DB_PATH = os.path.join(DB_DIR, "ebird.db")
os.makedirs(DB_DIR, exist_ok=True)

def load_notable_birds_to_sqlite(df: pd.DataFrame, db_path: str = DB_PATH):
    """
    Save notable birds DataFrame to SQLite database.
    """
    with sqlite3.connect(db_path) as conn:
        df.to_sql("notable_birds", conn, if_exists="replace", index=False)
        print(f"Loaded notable birds into SQLite database at {db_path}")

def load_species_observations_to_sqlite(
    transformed_species: Dict[str, pd.DataFrame],
    db_path: str = DB_PATH
):
    """
    Save species observations to SQLite database.
    Each species will have its own table.
    """
    with sqlite3.connect(db_path) as conn:
        for species_code, df in transformed_species.items():
            table_name = f"species_{species_code}"
            df.to_sql(table_name, conn, if_exists="replace", index=False)
            print(f"Loaded {species_code} observations into table '{table_name}' at {db_path}")

def load_states_to_sqlite(states_df: pd.DataFrame, db_path: str = DB_PATH):
    """
    Save states reference table to SQLite database.
    """
    with sqlite3.connect(db_path) as conn:
        states_df.to_sql("states", conn, if_exists="replace", index=False)
        print(f"Loaded states table into SQLite database at {db_path}")

def load_state_hotspot_stats(state_stats: pd.DataFrame, db_path: str = DB_PATH):
    with sqlite3.connect(db_path) as conn:
        state_stats.to_sql(
            "state_hotspot_stats",
            conn,
            if_exists="replace",
            index=False
        )
        print(f"Loaded state_hotspot_stats table into SQLite database at {db_path}")