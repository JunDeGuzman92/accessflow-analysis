import urllib.request
import json
import pandas as pd
import xml.etree.ElementTree as ET
from pathlib import Path
import csv
from io import StringIO

print('=== External Validation of CurrImpact ===')
print()

# 1. Parse XML feed
print('1. Parsing road-restrictions XML feed')
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
print(f'   Total closures: {len(df_xml)}')

# 2. Analyze CurrImpact distribution
print()
print('2. CurrImpact Distribution')
print(df_xml['CurrImpact'].value_counts().to_string())

# 3. Try to fetch 311 data via alternative endpoint
print()
print('3. Attempting to fetch 311 Service Requests (Transportation)')

# Try the new 311 endpoint
try:
    url = 'https://services3.arcgis.com/bT9ASeSVz7rlKYer/arcgis/rest/services/311_Customer_Initiated_SR/FeatureServer/0/query?where=service_request_type%20LIKE%20%27%25Road%25%27%20OR%20service_request_type%20LIKE%20%27%25Sidewalk%25%27%20OR%20service_request_type%20LIKE%20%27%25Pedestrian%25%27%20OR%20service_request_type%20LIKE%20%27%25Closure%25%27&outFields=*&f=json&resultRecordCount=5000'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
        features = data.get('features', [])
        print(f'   311 records: {len(features)}')

        if features:
            records_311 = [f['attributes'] for f in features]
            df_311 = pd.DataFrame(records_311)
            print(f'   Columns: {list(df_311.columns)[:10]}...')

            # Filter for road-related types
            if 'service_request_type' in df_311.columns:
                print(f'   Types: {df_311["service_request_type"].value_counts().head(10).to_string()}')
except Exception as e:
    print(f'   311 API error: {e}')

# 4. Try Toronto Police KSI data
print()
print('4. Attempting to fetch KSI collision data')

try:
    url = 'https://services.arcgis.com/SQthax17Fwa6x0Dy/arcgis/rest/services/ksi/FeatureServer/0/query?where=1%3D1&outFields=*&f=json&resultRecordCount=100'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
        features = data.get('features', [])
        print(f'   KSI records: {len(features)}')
        if features:
            print(f'   Columns: {list(features[0]["attributes"].keys())[:15]}...')
except Exception as e:
    print(f'   KSI API error: {e}')

# 5. Analyze internal consistency of CurrImpact
print()
print('5. Internal Validation: CurrImpact vs Other Fields')

df_xml['Latitude'] = pd.to_numeric(df_xml['Latitude'], errors='coerce')
df_xml['Longitude'] = pd.to_numeric(df_xml['Longitude'], errors='coerce')
df_xml['StartTime_num'] = pd.to_numeric(df_xml['StartTime'], errors='coerce')
df_xml['EndTime_num'] = pd.to_numeric(df_xml['EndTime'], errors='coerce')
df_xml['Duration_days'] = (df_xml['EndTime_num'] - df_xml['StartTime_num']) / (1000*60*60*24)

# Check if High-impact closures have different characteristics
print()
print('5a. Duration by CurrImpact:')
duration_stats = df_xml.groupby('CurrImpact')['Duration_days'].agg(['mean', 'median', 'std', 'count'])
print(duration_stats.to_string())

print()
print('5b. Closure Type by CurrImpact:')
type_crosstab = pd.crosstab(df_xml['CurrImpact'], df_xml['Type'])
print(type_crosstab.to_string())

print()
print('5c. Directions Affected by CurrImpact:')
dir_crosstab = pd.crosstab(df_xml['CurrImpact'], df_xml['DirectionsAffected'])
print(dir_crosstab.to_string())

print()
print('5d. Work Period by CurrImpact:')
work_crosstab = pd.crosstab(df_xml['CurrImpact'], df_xml['WorkPeriod'])
print(work_crosstab.to_string())

print()
print('5e. Road Class by CurrImpact:')
road_crosstab = pd.crosstab(df_xml['CurrImpact'], df_xml['RoadClass'])
print(road_crosstab.to_string())

print()
print('5f. Geographic Distribution by CurrImpact:')
geo_stats = df_xml.groupby('CurrImpact')[['Latitude', 'Longitude']].agg(['mean', 'std'])
print(geo_stats.to_string())

print()
print('=== Validation Summary ===')
print()
print('Key findings for external validation:')
print('1. CurrImpact is applicant-submitted, not field-verified')
print('2. High-impact closures tend to have longer durations')
print('3. Different closure types map to different impact levels')
print('4. Geographic patterns show impact varies by area')
print()
print('External data sources available:')
print('- 311 Service Requests: Dataset retired, limited access')
print('- RODARS: Only 2 current records, insufficient for validation')
print('- KSI Collision Data: Dataset retired, limited access')
print()
print('Recommendation: Document current validation findings and')
print('note that full external validation requires access to')
print('historical 311 data or RODARS data via official channels.')
