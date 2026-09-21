import sqlite3
conn = sqlite3.connect('C:/Users/junbu/Documents/accessflow-analysis/data/processed/massing.mbtiles')
cur = conn.cursor()

# Check for tiles near downtown Toronto at z16
# Toronto downtown: lat ~43.653, lon ~-79.383
# XYZ at z16: x=18340, y=22996 (approx)
# TMS y = (2^16 - 1) - XYZ_y = 65535 - 22996 = 42539
print("=== z16 tile at xyz 18340/22996 (TMS 18340/42539) ===")
for row in cur.execute("SELECT tile_column, tile_row, length(tile_data) FROM tiles WHERE zoom_level=16 AND tile_column BETWEEN 18335 AND 18345 AND tile_row BETWEEN 42530 AND 42545"):
    print(f"  TMS z16/{row[0]}/{row[1]}: {row[2]} bytes")

# Try the TMS y-flip
print("\n=== z12 sample tiles with y-flip check ===")
for row in cur.execute("SELECT zoom_level, tile_column, tile_row, length(tile_data) FROM tiles WHERE zoom_level=12 AND tile_column BETWEEN 1140 AND 1150"):
    xyz_y = (2**row[0] - 1) - row[2]
    print(f"  TMS z{row[0]}/{row[1]}/{row[2]} = XYZ z{row[0]}/{row[1]}/{xyz_y}: {row[3]} bytes")

# Check total tiles per zoom
print("\n=== Total tile data per zoom ===")
for row in cur.execute("SELECT zoom_level, count(*), sum(length(tile_data)) FROM tiles GROUP BY zoom_level ORDER BY zoom_level"):
    print(f"  z{row[0]}: {row[1]} tiles, {row[2]/1024/1024:.1f} MB")

conn.close()
