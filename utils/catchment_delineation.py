import os
import pathlib

import elevatr
import geopandas as gpd
from whitebox_workflows import WbEnvironment

rmap_before = None


def delineate_catchments(
    rmap: gpd.GeoDataFrame,
    wbe_folder: pathlib.Path,
    tile_folder: pathlib.Path,
) -> gpd.GeoDataFrame:
    """
    Delineate catchments for the provided risk map using WhiteboxTools.

    This function uses WhiteboxTools to fill depressions, calculate flow
    directions, and extract watersheds based on the provided risk map.

    It requires the WhiteboxTools environment to be set up and uses
    elevatr to obtain elevation data for the area of interest.

    Parameters
    ----------
    rmap : gpd.GeoDataFrame
        GeoDataFrame containing the risk map with geometry and river index.
    wbe_folder : pathlib.Path
        Path to the folder where WhiteboxTools will store its working files.
    tile_folder : pathlib.Path
        Path to the folder where elevation tiles will be stored.
    Returns
    -------
    gpd.GeoDataFrame
        GeoDataFrame containing the delineated catchments as polygons.

    """
    global rmap_before
    if rmap_before is not None and rmap_before.equals(rmap):
        return gpd.read_file(
            pathlib.Path.joinpath(wbe_folder, "polygons.shp").as_posix()
        ).to_crs(rmap.crs)
    rmap_before = rmap.copy()

    os.makedirs(wbe_folder, exist_ok=True)
    wbe = WbEnvironment()
    wbe.verbose = False
    wbe.working_directory = wbe_folder.as_posix()
    os.makedirs(tile_folder, exist_ok=True)

    buffer = 0.15
    bounds = rmap.to_crs(epsg=4326).total_bounds
    bounds[0] -= buffer
    bounds[1] -= buffer
    bounds[2] += buffer
    bounds[3] += buffer
    rs = elevatr.get_elev_raster(
        tuple(bounds),
        zoom=12,
        use_cache=True,
        delete_cache=False,
        crs="EPSG:4326",
        cache_folder=str(tile_folder),
        verbose=False,
    )
    rs.to_tif(pathlib.Path.joinpath(wbe_folder, "raster.tif").as_posix())
    rs = wbe.read_raster("raster.tif")
    filled = wbe.fill_depressions(rs)
    d8s = wbe.d8_pointer(filled)
    accum = wbe.d8_flow_accum(
        d8s, out_type="cells", clip=False, input_is_pointer=True
    )
    streams = wbe.extract_streams(accum, threshold=1000)
    rmap.to_crs(epsg=4326)["geometry"].to_file(
        pathlib.Path.joinpath(wbe_folder, "riskmap.shp").as_posix()
    )
    points = wbe.read_vector("riskmap.shp")
    snapped = wbe.jenson_snap_pour_points(points, streams, snap_dist=0.001)
    watersheds = wbe.watershed(
        d8_pointer=d8s, pour_points=snapped, esri_pntr=False
    )
    polygons = wbe.raster_to_vector_polygons(watersheds)
    wbe.write_vector(polygons, "polygons.shp")
    polygons = gpd.read_file(
        pathlib.Path.joinpath(wbe_folder, "polygons.shp").as_posix()
    ).to_crs(rmap.crs)
    return polygons
