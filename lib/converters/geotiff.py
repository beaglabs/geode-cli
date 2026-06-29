"""
Hematite CLI — GeoTIFF to Zarr converter.

Uses rasterio + rioxarray to read GeoTIFF and write as Zarr.
Multi-band GeoTIFFs are stored as a single Zarr array with a band dimension.
"""

import os
import tempfile
import rasterio
import xarray as xr
import numpy as np


def convert(filepath: str) -> str:
    output_dir = os.path.join(
        tempfile.gettempdir(),
        f"hematite-{os.path.basename(filepath)}.zarr",
    )

    with rasterio.open(filepath) as src:
        data = src.read()
        crs = src.crs.to_string() if src.crs else None
        transform = list(src.transform) if src.transform else None

        if src.count == 1:
            arr = xr.DataArray(
                data[0],
                dims=["y", "x"],
                coords={
                    "y": np.arange(src.height),
                    "x": np.arange(src.width),
                },
                attrs={"crs": crs, "transform": transform},
            )
        else:
            arr = xr.DataArray(
                data,
                dims=["band", "y", "x"],
                coords={
                    "band": np.arange(1, src.count + 1),
                    "y": np.arange(src.height),
                    "x": np.arange(src.width),
                },
                attrs={"crs": crs, "transform": transform, "band_descriptions": list(src.descriptions)},
            )

    ds = xr.Dataset({"data": arr})
    ds.to_zarr(output_dir, mode="w")
    return output_dir