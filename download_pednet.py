import urllib.request
import csv
from io import StringIO

print('=== Downloading Toronto Pedestrian Network ===')

# Download CSV version (smaller than GeoJSON)
url = 'https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/4b5c7a84-dea1-4137-875d-71d7f662c83f/resource/33865740-bdf4-4876-a498-c198ce0f1484/download/pedestrian-network-data-4326.csv'

try:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60) as resp:
        content = resp.read().decode('utf-8')
        print(f'Downloaded {len(content)} bytes')

        # Parse CSV
        reader = csv.DictReader(StringIO(content))
        rows = list(reader)
        print(f'Total edges: {len(rows)}')

        if rows:
            print(f'Columns: {list(rows[0].keys())}')
            print()
            print('Sample row:')
            for k, v in rows[0].items():
                print(f'  {k}: {v}')

except Exception as e:
    print(f'Error: {e}')
    print()
    print('Trying alternative URL...')

    # Try the Toronto Open Data direct CSV
    url2 = 'https://ckan0.cf.opendata.inter.prod-toronto.ca/datastore/dump/93b36f84-4a25-4b22-9812-44912ca34e02'
    try:
        req = urllib.request.Request(url2, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as resp:
            content = resp.read().decode('utf-8')
            print(f'Downloaded {len(content)} bytes')
            # Check if it's JSON (GeoJSON)
            if content.startswith('{'):
                print('Got GeoJSON format')
            else:
                print('Got CSV format')
    except Exception as e2:
        print(f'Alternative error: {e2}')
