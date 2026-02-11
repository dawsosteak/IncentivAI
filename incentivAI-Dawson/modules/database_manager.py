import pandas as pd
from pathlib import Path
from datetime import datetime
from config import OUTPUT_DIR, DATABASE_FILE

class DatabaseManager:
    def __init__(self):
        Path(OUTPUT_DIR).mkdir(exist_ok=True)
        self.path = Path(OUTPUT_DIR) / DATABASE_FILE
        self.df = pd.DataFrame()

    def add(self, record):
        record["date_scraped"] = datetime.utcnow().isoformat()
        self.df = pd.concat([self.df, pd.DataFrame([record])])

    def save(self):
        self.df.to_csv(self.path, index=False)
