import pandas as pd
import os

try:
    excel_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Extracted_Incentives.xlsx')
    if not os.path.exists(excel_path):
        excel_path = '../Extracted_Incentives.xlsx' # Fallback
    
    df = pd.read_excel(excel_path)
    print("Columns:", df.columns.tolist())
    print("-" * 20)
    for index, row in df.iterrows():
        print(f"Row {index}:")
        for col in df.columns:
            print(f"  {col}: {row[col]}")
        print("-" * 20)
except Exception as e:
    print(f"Error reading Excel: {e}")
