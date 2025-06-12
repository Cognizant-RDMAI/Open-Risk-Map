from collections import defaultdict

import geopandas as gpd
import momepy
import networkx as nx
import numpy as np
import pandas as pd
import shapely


def add_location_on_river_and_closest_edge(
    rivers: gpd.GeoDataFrame,
    geometry: gpd.GeoSeries,
    max_dist_from_river: float,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Find the closest points on the river network for given geometries.

    Parameters
    ----------
    rivers : gpd.GeoDataFrame
        Rivers represented by LineStrings.
    geometry : gpd.GeoSeries
        Geometries of the points for which to find the closest river points.
    max_dist_from_river : float
        Maximum distance for finding the closest river segment.

    Returns
    -------
    tuple[pd.Series, pd.Series, pd.Series]
        A tuple containing Series of the closest points, edges on the river
        network, and the riverID.
    """

    def find_shortest_line(
        p: shapely.Point, idx: float | None, rivers_df: gpd.GeoDataFrame
    ) -> shapely.LineString | None:
        if not idx > 0:
            return None
        return shapely.shortest_line(p, rivers_df.iloc[int(idx)].geometry)

    def get_line_endpoint(
        line: shapely.LineString | None,
    ) -> shapely.Point | None:

        if line is None:
            return None
        return shapely.Point(line.coords[-1])

    def return_linestring_coords(x: shapely.LineString | None):
        if pd.isna(x):
            return None
        else:
            return tuple(x.coords)

    gdf = gpd.GeoDataFrame(geometry=geometry, crs=geometry.crs)
    rivers["closestEdge"] = rivers.geometry.copy()
    nearest_point_info = gpd.sjoin_nearest(
        gdf,
        rivers[["geometry", "riverID", "closestEdge"]],
        max_distance=max_dist_from_river,
        how="left",
    )
    rivers.drop("closestEdge", axis=1)
    nearest_point_info = nearest_point_info[
        ~nearest_point_info.index.duplicated(keep="first")
    ]
    connecting_lines = nearest_point_info.apply(
        lambda x: find_shortest_line(x["geometry"], x["index_right"], rivers),
        axis=1,
    ).set_crs(nearest_point_info.crs)
    nearest_point_info.drop(columns=["index_right"], inplace=True)
    nearest_point_info["closestPoint"] = connecting_lines.apply(
        get_line_endpoint
    ).set_crs(nearest_point_info.crs)
    nearest_point_info["closestEdge"] = nearest_point_info[
        "closestEdge"
    ].apply(return_linestring_coords)
    return (
        nearest_point_info["closestPoint"],
        nearest_point_info["closestEdge"],
        nearest_point_info["riverID"],
    )


def river_to_graph(
    rivers: gpd.GeoDataFrame, directed: bool
) -> nx.DiGraph | nx.Graph:
    """
    Convert a GeoDataFrame of rivers into a NetworkX graph.

    Parameters
    ----------
    rivers : gpd.GeoDataFrame
        GeoDataFrame containing river data.
    directed : bool
        Indicates whether the resulting graph should be directed.

    Returns
    -------
    nx.Graph
        The NetworkX graph representing the river network.
    """
    river_graph = momepy.gdf_to_nx(
        rivers,
        approach="primal",
        directed=directed,  # To indicate flow direction
        multigraph=False,
    )

    # Create a dictionary to store edge IDs for each node
    node_edge_ids = defaultdict(set)

    # Populate the dictionary by iterating over edges
    for u, v, data in river_graph.edges(data=True):
        edge_id = data.get("riverID")
        node_edge_ids[u].add(edge_id)
        node_edge_ids[v].add(edge_id)
    nx.set_node_attributes(river_graph, node_edge_ids, name="riverID")
    return river_graph


def split_rivers(
    rivers: gpd.GeoDataFrame, resolution: float, river_df_id_col: str
) -> gpd.GeoDataFrame:
    """
    Split a GeoDataFrame of LineStrings into smaller LineStrings of a
    specified maximum resolution.

    Parameters
    ----------
    rivers : gpd.GeoDataFrame
        The input GeoDataFrame containing LineStrings.
    resolution : float
        The desired maximum resolution to split the LineStrings.
    river_df_id_col : str
        The column name containing unique river IDs.

    Returns
    -------
    gpd.GeoDataFrame
        A GeoDataFrame with split LineStrings and the original river IDs.
    """

    rivers2 = rivers.copy()

    # Check if anything given is not a LineString
    if rivers2.geometry.apply(
        lambda x: not isinstance(x, shapely.LineString)
    ).any():
        raise Exception(
            "riversdf has other geometries. This function only works on"
            "linestrings"
        )

    def split_linestring(line: shapely.LineString) -> list[shapely.LineString]:
        points: np.ndarray[shapely.Point] = shapely.line_interpolate_point(
            line,
            np.arange(0, line.length, resolution),
            # np.linspace(0,1,n_divisions),
            # normalized=True,
        )

        endpoint = shapely.Point(line.coords[-1])
        if endpoint not in points:
            points = np.append(points, endpoint)

        return [
            shapely.LineString([p1, p2])
            for p1, p2 in zip(points[:-1], points[1:])
        ]

    rivers2["geometry2"] = rivers2.geometry.apply(split_linestring)

    rivers2 = rivers2[["riverID", "geometry2"]].explode("geometry2")
    rivers2.rename(columns={"geometry2": "geometry"}, inplace=True)

    rivers2.geometry = rivers2.geometry.astype("geometry")
    rivers2 = gpd.GeoDataFrame(rivers2)
    rivers2.geometry = rivers2.geometry.set_crs(rivers.crs)
    rivers2.reset_index(inplace=True)
    return rivers2


FLOW_ACCUM_COEFF = 1.476e-5  # m2/s


def linear_flow(accum_len: float, flow_coeff: float = None) -> float:
    """linear_flow gives a linear approximation of the river flow(m3/sec)
    given the upstream accumulated length

    Parameters
    ----------
    accum_len : float
        The upstream accumulated length in meters
    flow_coeff : float, optional
        The coefficient to give the river flow, by default None

    Returns
    -------
    float
        The river flow in m3/sec
    """
    if flow_coeff is None:
        flow_coeff = FLOW_ACCUM_COEFF
    return flow_coeff * accum_len
