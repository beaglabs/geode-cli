"""
Hematite CLI — Vector to Arrow converter.

Converts Shapefile, GeoJSON, and Parquet to Arrow IPC stream format.
Uses geopandas + pyarrow.
"""

import os
import tempfile
import geopandas as gpd
import pyarrow as pa
import pyarrow.ipc as ipc


def convert(filepath: str) -> str:
    output_path = os.path.join(
        tempfile.gettempdir(),
        f"hematite-{os.path.basename(filepath)}.arrow",
    )

    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".parquet":
        gdf = gpd.read_parquet(filepath)
    elif ext == ".geojson":
        gdf = gpd.read_file(filepath)
    elif ext == ".shp":
        gdf = gpd.read_file(filepath)
    else:
        gdf = gpd.read_file(filepath)

    table = pa.Table.from_pandas(gdf)

    with pa.OSFile(output_path, "wb") as sink:
        writer = ipc.new_stream(sink, table.schema)
        writer.write_table(table)
        writer.close()

    return output_path