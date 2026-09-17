import urllib.request
import json
import pandas as pd
import xml.etree.ElementTree as ET
from pathlib import Path

# 1. Query RODARS for current road restrictions
print('=== Fetching RODARS data ===')
url = 'https://gis.toronto.ca/arcgis/rest/services/cot_geospatial2/FeatureServer/5/query?where=1%3D1&outFields=*&f=json&resultRecordCount=2000'
req = urllib.request.Request(url, headers={'User-Agent': 'Python'})
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.load(resp)

rodars_features = data.get('features', [])
print(f'RODARS features: {len(rodars_features)}')

if rodars_features:
    # Convert to DataFrame
    rodars_records = [f['attributes'] for f in rodars_features]
    df_rodars = pd.DataFrame(rodars_records)
    print(f'RODARS columns: {list(df_rodars.columns)}')
    print()
    print('RODARS sample (first 3 rows):')
    print(df_rodars.head(3).to_string())
    print()

    # 2. Parse XML feed
    print('=== Parsing XML feed ===')
    xml_path = Path('fixtures/road-restrictions--resource-3afea38a-baad-4f39-b22f-d608875e1746.xml')
    tree = ET.parse(xml_path)
    root = tree.getroot()
    records = []
    for closure in root.findall('.//Closure'):
        record = {}
        for field in closure:
            record[field.tag] = field.text
        records.append(record)
    df_xml = pd.DataFrame(records)
    print(f'XML closures: {len(df_xml)}')

    # 3. Compare CurrImpact from XML with RODARS data
    print()
    print('=== External Validation: CurrImpact vs RODARS ===')

    # Check RODARS status distribution
    if 'STATUS' in df_rodars.columns:
        print(f'RODARS STATUS distribution:')
        print(df_rodars['STATUS'].value_counts())
        print()

    # Check RODARS road closure type
    if 'ROAD_CLOSURE_TYPE' in df_rodars.columns:
        print(f'RODARS ROAD_CLOSURE_TYPE distribution:')
        print(df_rodars['ROAD_CLOSURE_TYPE'].value_counts())
        print()

    # Check RODARS issue type
    if 'ISSUE_TYPE' in df_rodars.columns:
        print(f'RODARS ISSUE_TYPE distribution:')
        print(df_rodars['ISSUE_TYPE'].value_counts())
        print()

    # Check RODARS work event type
    if 'WORK_EVENT_TYPE' in df_rodars.columns:
        print(f'RODARS WORK_EVENT_TYPE distribution:')
        print(df_rodars['WORK_EVENT_TYPE'].value_counts().head(10))
        print()

    # 4. Match XML closures to RODARS by location
    print('=== Location-based matching ===')

    # Convert RODARS coordinates to numeric
    for col in ['RR_LATITUDE', 'RR_LONGITUDE']:
        if col in df_rodars.columns:
            df_rodars[col] = pd.to_numeric(df_rodars[col], errors='coerce')

    # Convert XML coordinates to numeric
    df_xml['Latitude'] = pd.to_numeric(df_xml['Latitude'], errors='coerce')
    df_xml['Longitude'] = pd.to_numeric(df_xml['Longitude'], errors='coerce')

    # Drop rows with missing coordinates
    df_rodars_geo = df_rodars.dropna(subset=['RR_LATITUDE', 'RR_LONGITUDE'])
    df_xml_geo = df_xml.dropna(subset=['Latitude', 'Longitude'])

    print(f'RODARS with coordinates: {len(df_rodars_geo)}')
    print(f'XML with coordinates: {len(df_xml_geo)}')

    # For each XML closure, find nearest RODARS point
    from scipy.spatial import cKDTree
    import numpy as np

    rodars_coords = df_rodars_geo[['RR_LATITUDE', 'RR_LONGITUDE']].values
    xml_coords = df_xml_geo[['Latitude', 'Longitude']].values

    tree = cKDTree(rodars_coords)
    distances, indices = tree.query(xml_coords, k=1)

    # Match threshold: 0.001 degrees (~100m)
    threshold = 0.001
    matched = distances < threshold
    print(f'Matched closures (within {threshold} degrees): {matched.sum()} / {len(xml_coords)}')

    # 5. Compare CurrImpact with RODARS data for matched closures
    if matched.sum() > 0:
        matched_xml = df_xml_geo[matched].copy()
        matched_rodars = df_rodars_geo.iloc[indices[matched]]

        print()
        print('=== CurrImpact vs RODARS for matched closures ===')

        # Add RODARS fields to matched XML
        matched_xml['RODARS_STATUS'] = matched_rodars['STATUS'].values if 'STATUS' in matched_rodars.columns else 'N/A'
        matched_xml['RODARS_CLOSURE_TYPE'] = matched_rodars['ROAD_CLOSURE_TYPE'].values if 'ROAD_CLOSURE_TYPE' in matched_rodars.columns else 'N/A'

        # Compare CurrImpact with RODARS status
        print('CurrImpact vs RODARS STATUS:')
        cross_tab = pd.crosstab(matched_xml['CurrImpact'], matched_xml['RODARS_STATUS'])
        print(cross_tab)
        print()

        # Compare CurrImpact with RODARS closure type
        print('CurrImpact vs RODARS CLOSURE_TYPE:')
        cross_tab2 = pd.crosstab(matched_xml['CurrImpact'], matched_xml['RODARS_CLOSURE_TYPE'])
        print(cross_tab2)
    else:
        print('No matches found. Check coordinate systems or thresholds.')
else:
    print('No RODARS data returned.')
