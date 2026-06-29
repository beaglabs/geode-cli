"""
Hematite CLI — GRIB to Zarr converter.

Uses cfgrib + xarray to read GRIB and write as Zarr.
"""

import os
import tempfile
import xarray as xr


def convert(filepath: str) -> str:
    output_dir = os.path.join(
        tempfile.gettempdir(),
        f"hematite-{os.path.basename(filepath)}.zarr",
    )

    ds = xr.open_dataset(filepath, engine="cfgrib")
    ds.to_zarr(output_dir, mode="w")
    ds.close()
    return output_dir