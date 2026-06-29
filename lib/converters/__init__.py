"""
Hematite CLI — Format converters dispatch table.

Maps file extensions to converter functions.
Imports are lazy — converters are only loaded when actually used.
"""

import importlib
import os

CONVERTER_MAP = {
    ".tif": ("geotiff", "convert"),
    ".tiff": ("geotiff", "convert"),
    ".nc": ("netcdf", "convert"),
    ".grib": ("grib", "convert"),
    ".grb": ("grib", "convert"),
    ".las": ("las", "convert"),
    ".laz": ("las", "convert"),
    ".shp": ("vector", "convert"),
    ".geojson": ("vector", "convert"),
    ".parquet": ("vector", "convert"),
}

ZARR_EXTENSIONS = {".tif", ".tiff", ".nc", ".grib", ".grb", ".las", ".laz"}
ARROW_EXTENSIONS = {".shp", ".geojson", ".parquet"}
ZARR_MARKERS = {".zarray", ".zgroup", "zarr.json"}


def output_type(ext: str, filepath: str = "") -> str:
    if ext in ZARR_EXTENSIONS:
        return "zarr"
    if ext in ARROW_EXTENSIONS:
        return "arrow"
    if _is_zarr_path(filepath):
        return "zarr"
    return "blob"


def can_convert(ext: str) -> bool:
    return ext in CONVERTER_MAP


def convert(filepath: str) -> str:
    """Convert file to Zarr or Arrow. Returns path to converted output."""
    ext = os.path.splitext(filepath)[1].lower()
    entry = CONVERTER_MAP.get(ext)
    if not entry:
        return filepath

    module_name, func_name = entry
    mod = importlib.import_module(f"{__package__}.{module_name}")
    converter = getattr(mod, func_name)
    return converter(filepath)


def _is_zarr_path(filepath: str) -> bool:
    return any(marker in filepath for marker in ZARR_MARKERS) or ".zarr/" in filepath or filepath.endswith(".zarr")
