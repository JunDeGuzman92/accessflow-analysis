import urllib.request
import json
import pandas as pd
import xml.etree.ElementTree as ET
from pathlib import Path

print('=== Trying RODARS MapServer (layer 76) ===')

# Try MapServer endpoint with more records
url = 'https://gis.toronto.ca/arcgis/rest/services/cot_geospatial2/MapServer/76/query?where=1%3D1&outFields=*&f=json&resultRecordCount=2000'
req = urllib.request.Request(url, headers={'User-Agent': 'Python'})
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.load(resp)

rodars_features = data.get('features', [])
print(f'RODARS features: {len(rodars_features)}')

if rodars_features:
    rodars_records = [f['attributes'] for f in rodars_features]
    df_rodars = pd.DataFrame(rodars_records)
    print(f'RODARS columns: {list(df_rodars.columns)}')
    print()

    # Check for key fields
    if 'STATUS' in df_rodars.columns:
        print('STATUS distribution:')
        print(df_rodars['STATUS'].value_counts())
        print()

    if 'ROAD_CLOSURE_TYPE' in df_rodars.columns:
        print('ROAD_CLOSURE_TYPE distribution:')
        print(df_rodars['ROAD_CLOSURE_TYPE'].value_counts().head(10))
        print()

    if 'PRIORITY' in df_rodars.columns:
        print('PRIORITY distribution:')
        print(df_rodars['PRIORITY'].value_counts().head(10))
        print()

    # Convert coordinates
    for col in ['FROM_ROAD_LATITUDE', 'FROM_ROAD_LONGITUDE']:
        if col in df_rodars.columns:
            df_rodars[col] = pd.to_numeric(df_rodars[col], errors='coerce')

    # Parse XML
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

    # Convert XML coordinates
    df_xml['Latitude'] = pd.to_numeric(df_xml['Latitude'], errors='coerce')
    df_xml['Longitude'] = pd.to_numeric(df_xml['Longitude'], errors='coerce')

    # Match by location
    from scipy.spatial import cKDTree
    import numpy as np

    rodars_geo = df_rodars.dropna(subset=['FROM_ROAD_LATITUDE', 'FROM_ROAD_LONGITUDE'])
    xml_geo = df_xml.dropna(subset=['Latitude', 'Longitude'])

    print(f'RODARS with coordinates: {len(rodars_geo)}')
    print(f'XML with coordinates: {len(xml_geo)}')

    if len(rodars_geo) > 0 and len(xml_geo) > 0:
        rodars_coords = rodars_geo[['FROM_ROAD_LATITUDE', 'FROM_ROAD_LONGITUDE']].values
        xml_coords = xml_geo[['Latitude', 'Longitude']].values

        tree = cKDTree(rodars_coords)
        distances, indices = tree.query(xml_coords, k=1)

        threshold = 0.002  # ~200m
        matched = distances < threshold
        print(f'Matched closures (within {threshold} degrees): {matched.sum()} / {len(xml_coords)}')

        if matched.sum() > 0:
            matched_xml = xml_geo[matched].copy()
            matched_rodars = rodars_geo.iloc[indices[matched]]

            print()
            print('=== CurrImpact vs RODARS STATUS ===')

            # Add RODARS fields
            matched_xml['RODARS_STATUS'] = matched_rodars['STATUS'].values if 'STATUS' in matched_rodars.columns else 'N/A'
            matched_xml['RODARS_CLOSURE_TYPE'] = matched_rodars['ROAD_CLOSURE_TYPE'].values if 'ROAD_CLOSURE_TYPE' in matched_rodars.columns else 'N/A'
            matched_xml['RODARS_PRIORITY'] = matched_rodars['PRIORITY'].values if 'PRIORITY' in matched_rodars.columns else 'N/A'

            # Compare
            print('CurrImpact vs RODARS STATUS:')
            print(pd.crosstab(matched_xml['CurrImpact'], matched_xml['RODARS_STATUS']))
            print()

            print('CurrImpact vs RODARS CLOSURE_TYPE:')
            print(pd.crosstab(matched_xml['CurrImpact'], matched_xml['RODARS_CLOSURE_TYPE']))
else:
    print('No RODARS data returned.')
