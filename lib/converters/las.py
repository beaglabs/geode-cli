"""
Hematite CLI — LAS/LAZ to Zarr converter.

Converts point cloud data to a structured Zarr array.
"""

import os
import tempfile
import numpy as np
import xarray as xr
import laspy


LAS_DIMENSIONS = ["x", "y", "z", "intensity", "classification", "return_number", "number_of_returns"]


def convert(filepath: str) -> str:
    output_dir = os.path.join(
        tempfile.gettempdir(),
        f"hematite-{os.path.basename(filepath)}.zarr",
    )

    with laspy.open(filepath) as f:
        las = f.read()
        point_count = len(las)

        data = {}
        for dim in LAS_DIMENSIONS:
            if hasattr(las, dim):
                data[dim] = las[dim]

        ds = xr.Dataset(
            {name: xr.DataArray(arr, dims=["point"]) for name, arr in data.items()},
            coords={"point": np.arange(point_count)},
            attrs={"source_format": "LAS" if filepath.endswith(".las") else "LAZ"},
        )

    ds.to_zarr(output_dir, mode="w")
    return output_dir