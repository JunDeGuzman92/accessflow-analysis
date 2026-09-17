import urllib.request
import json
import pandas as pd
import xml.etree.ElementTree as ET
from pathlib import Path

print('=== Fetching 311 Service Requests ===')

# 311 Service Requests - Customer Initiated
# Try to get recent data
url = 'https://ckan0.cf.opendata.api/datastore/search?resource_id=2c576c4e-5a72-492f-bc8a-8464a3e5e34f&limit=5000'
req = urllib.request.Request(url, headers={'User-Agent': 'Python'})
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
        records = data.get('records', [])
        print(f'311 records: {len(records)}')
        if records:
            df_311 = pd.DataFrame(records)
            print(f'311 columns: {list(df_311.columns)}')
            print()
            print('Sample:')
            print(df_311.head(3).to_string())
except Exception as e:
    print(f'311 API error: {e}')

# Alternative: Try Toronto Open Data direct download
print()
print('=== Trying alternative 311 endpoint ===')
url2 = 'https://ckan0.cf.opendata.api/datastore/search?resource_id=2c576c4e-5a72-492f-bc8a-8464a3e5e34f&limit=100'
req2 = urllib.request.Request(url2, headers={'User-Agent': 'Python'})
try:
    with urllib.request.urlopen(req2, timeout=30) as resp:
        data2 = json.load(resp)
        records2 = data2.get('records', [])
        if records2:
            df_311 = pd.DataFrame(records2)
            print(f'311 columns: {list(df_311.columns)}')

            # Filter for road-related complaints
            road_keywords = ['road', 'street', 'sidewalk', 'pedestrian', 'closure', 'blocked']
            if 'service_request_type' in df_311.columns:
                road_mask = df_311['service_request_type'].str.contains('|'.join(road_keywords), case=False, na=False)
                print(f'Road-related complaints: {road_mask.sum()} / {len(df_311)}')
                if road_mask.sum() > 0:
                    print(df_311[road_mask]['service_request_type'].value_counts().head(10))

            # Check for location fields
            for col in ['latitude', 'longitude', 'lat', 'lon']:
                if col in df_311.columns:
                    print(f'Has {col}: yes')
except Exception as e:
    print(f'311 API error: {e}')
