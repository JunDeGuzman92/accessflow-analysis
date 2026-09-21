import xml.etree.ElementTree as ET
from pathlib import Path

tree = ET.parse(list(Path("fixtures").glob("road-restrictions--resource-*.xml"))[0])
root = tree.getroot()
closures = root.findall(".//Closure")

c = closures[0]
print("Fields:", [f.tag for f in c])
lat = c.find("Latitude")
lon = c.find("Longitude")
poly = c.find("Polyline")
print(f"Lat={lat.text if lat is not None else None}, Lon={lon.text if lon is not None else None}")
if poly is not None and poly.text:
    print(f"Polyline={poly.text[:150]}")

has_lat = sum(1 for c in closures if c.find("Latitude") is not None and c.find("Latitude").text)
has_poly = sum(1 for c in closures if c.find("Polyline") is not None and c.find("Polyline").text and c.find("Polyline").text.strip())
print(f"Has lat/lon: {has_lat}/{len(closures)}")
print(f"Has polyline: {has_poly}/{len(closures)}")
