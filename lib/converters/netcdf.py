"""
Hematite CLI — NetCDF to Zarr converter.

Uses xarray to open NetCDF and write as Zarr.
"""

import os
import tempfile
import xarray as xr


def convert(filepath: str) -> str:
    output_dir = os.path.join(
        tempfile.gettempdir(),
        f"hematite-{os.path.basename(filepath)}.zarr",
    )

    ds = xr.open_dataset(filepath)
    ds.to_zarr(output_dir, mode="w")
    ds.close()
    return output_dir