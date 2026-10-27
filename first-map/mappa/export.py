"""Exports in formats responders already open: GeoTIFF, GeoPackage, GeoJSON, KML, CSV."""
from __future__ import annotations

import shutil
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import simplekml
from affine import Affine
from rasterio.enums import Resampling
from rasterio.features import shapes
from shapely.geometry import shape

from .roads import BLOCKED, CLEAR, NODATA, UNCERTAIN

KML_COLOURS = {BLOCKED: "ff0000ff", UNCERTAIN: "ff00a5ff", CLEAR: "ff00c800", NODATA: "ff999999"}  # aabbggrr
WGS84 = "EPSG:4326"


def corrected_transform(orig: Affine, grid_tf: Affine, M: np.ndarray) -> Affine:
    """New full-res ortho transform = G * M_corner * G^-1 * T_orig (translation/rotation applied to the
    georeference only; pixels are never resampled). M is in OpenCV pixel-centre coordinates."""
    half = Affine.translation(0.5, 0.5)
    Mc = half @ Affine(*M.flatten()) @ ~half
    return grid_tf @ Mc @ ~grid_tf @ orig


def write_corrected_ortho(src_path: str, dst_path: str, M: np.ndarray, grid_tf: Affine):
    shutil.copyfile(src_path, dst_path)
    with rasterio.open(dst_path, "r+") as ds:
        ds.transform = corrected_transform(ds.transform, grid_tf, M)


def write_raster(path, arr, grid, dtype, nodata=None, overviews=True):
    arr = arr if arr.ndim == 3 else arr[None]
    with rasterio.open(path, "w", driver="GTiff", height=grid.height, width=grid.width, count=arr.shape[0],
                       dtype=dtype, crs=grid.crs, transform=grid.transform, compress="deflate",
                       tiled=True, blockxsize=256, blockysize=256, nodata=nodata) as dst:
        dst.write(arr.astype(dtype))
        if overviews and min(grid.shape) > 512:
            dst.build_overviews([2, 4, 8], Resampling.nearest if dtype == "uint8" else Resampling.average)


def mask_to_polygons(mask: np.ndarray, grid, min_area_m2: float = 0.0) -> gpd.GeoDataFrame:
    geoms = [shape(g) for g, v in shapes(mask.astype(np.uint8), mask=mask.astype(bool), transform=grid.transform) if v == 1]
    gdf = gpd.GeoDataFrame({"geometry": geoms}, crs=grid.crs)
    gdf["geometry"] = gdf.geometry.simplify(grid.res * 0.7)
    gdf["area_m2"] = gdf.geometry.area.round(0)
    gdf = gdf[gdf.area_m2 >= min_area_m2].reset_index(drop=True)
    gdf["change_id"] = gdf.index
    return gdf


def write_vector(gdf: gpd.GeoDataFrame, stem: Path, layer: str):
    """GeoPackage in the working CRS + GeoJSON in WGS84 (RFC 7946)."""
    gdf.to_file(f"{stem}.gpkg", layer=layer, driver="GPKG")
    gdf.to_crs(WGS84).to_file(f"{stem}.geojson", driver="GeoJSON")


def write_roads_kml(scored: gpd.GeoDataFrame, path: str, title: str, note: str):
    kml = simplekml.Kml(name=title)
    kml.document.description = note
    wgs = scored.to_crs(WGS84)
    folders = {s: kml.newfolder(name=s) for s in (BLOCKED, UNCERTAIN, CLEAR, NODATA)}
    for _, r in wgs.iterrows():
        ls = folders[r.status].newlinestring(name=f"{r['name']} #{r.seq}", coords=list(r.geometry.coords))
        ls.description = f"{r.status}: changed {r.changed_frac}, height anomaly {r.height_anom_m} m, length {r.length_m} m"
        ls.style.linestyle.color = KML_COLOURS[r.status]
        ls.style.linestyle.width = 6 if r.status == BLOCKED else 3
    kml.save(path)


def write_changes_kml(changes: gpd.GeoDataFrame, path: str, title: str):
    kml = simplekml.Kml(name=title)
    for _, r in changes.to_crs(WGS84).iterrows():
        geoms = r.geometry.geoms if r.geometry.geom_type == "MultiPolygon" else [r.geometry]
        for g in geoms:
            p = kml.newpolygon(name=f"change {r.change_id} ({r.area_m2:.0f} m2)", outerboundaryis=list(g.exterior.coords))
            p.style.polystyle.color = "660000ff"
            p.style.linestyle.color = "ff0000ff"
    kml.save(path)
