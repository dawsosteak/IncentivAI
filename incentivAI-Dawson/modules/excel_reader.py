import pandas as pd
from config import DEFAULT_URL_COLUMN

def get_urls_from_excel(path):
    df = pd.read_excel(path)
    return (
        df[DEFAULT_URL_COLUMN]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )
