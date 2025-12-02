# Configure logger
import logging
import pathlib
from collections.abc import Callable

import geopandas as gpd
import momepy
import networkx as nx
import pandas as pd
import shapely
from typing_extensions import Self

import utils.rivers
from utils import catchment_delineation, graph

logger = logging.getLogger(__name__)

"""
RiskMap Class
=============

A class for creating risk maps based on river networks and point locations.

This class provides methods to process river data, construct river networks,
and analyze risk propagation from point locations along the river network.

"""


class RiskMap:
    """
    A class for creating risk maps based on river networks and point locations.

    This class provides methods to process river data, construct river
    networks, and analyze risk propagation from point locations along the
    river network.

    All work is done in EPSG 27700.

    Parameters
    ----------
    riversdf : gpd.GeoDataFrame
        GeoDataFrame containing river data as LineStrings.
    id_col : str
        Column name in the river GeoDataFrame that contains unique river IDs.
    resolution : float
        Desired resolution for splitting river LineStrings into smaller segments.
    river_flow_func: Callable
        A function from the row dict of the riversdf to a float which defines
        the river flow in m3/s.
    catchment_mask : gpd.GeoDataFrame | None, optional
        A GeoDataFrame that serves as a mask for delineating catchments.
        If provided, catchments will be clipped to this mask. Default is None.

    Attributes
    ----------
    __rivers : gpd.GeoDataFrame
        Processed river data.
    __rivers_split : gpd.GeoDataFrame
        River data split into smaller segments based on the resolution.
    __risk_map : gpd.GeoDataFrame | None
        GeoDataFrame representing the risk map.
    __river_network : nx.Graph | None
        NetworkX graph representing the river network.
    __joined_catchments : gpd.GeoDataFrame | None
        GeoDataFrame containing delineated catchments.
    __map_poly_join : pd.DataFrame | None
        DataFrame mapping between catchments to join and their FIDs
    __mapping_points : pd.DataFrame | None
        DataFrame containing mapping points from the risk map to catchments
    """

    def __init__(
        self,
        riversdf: gpd.GeoDataFrame,
        id_col: str,
        resolution: float,
        river_flow_func: Callable,
        catchment_mask: gpd.GeoDataFrame | None = None,
    ):

        # Check if column in rivers
        if id_col not in riversdf.columns:
            raise ValueError(
                f"River id column [{id_col}] not in river dataframe columns"
            )
        riversdf = riversdf.to_crs(epsg=27700).rename(
            columns={id_col: "riverID"}
        )
        self.__rivers: gpd.GeoDataFrame = riversdf
        self.__rivers["flow"] = riversdf.apply(river_flow_func, axis=1)

        self.__rivers_split: gpd.GeoDataFrame = utils.rivers.split_rivers(
            self.__rivers,
            resolution,
        )

        self.__rivers.set_index("riverID", inplace=True)

        self.construct_river_graph()
        self.__construct_risk_map()

        self.__joined_catchments = None
        self.__map_poly_join = None
        self.__mapping_points = None
        self.__catchment_mask = catchment_mask

    def __repr__(self) -> str:
        """
        Return the risk map as a GeoDataFrame if it has been constructed.

        Returns
        -------
        gpd.GeoDataFrame | None
            The risk map GeoDataFrame if constructed, otherwise None.
        """
        return self.__risk_map.__repr__()

    # Getter functions
    def get_rivers(self, copy: bool = True) -> gpd.GeoDataFrame:
        """get_rivers returns the rivers from the RiskMap

        Parameters
        ----------
        copy : bool, optional
            Whether to return a copy or the original GeoDataFrame, by default
            True

        Returns
        -------
        gpd.GeoDataFrame
            The rivers dataframe
        """
        if copy:
            return self.__rivers.copy()
        else:
            return self.__rivers

    def get_rivers_split(self, copy: bool = True) -> gpd.GeoDataFrame:
        """get_rivers returns the rivers which are discretized from the RiskMap

        Parameters
        ----------
        copy : bool, optional
            Whether to return a copy or the original GeoDataFrame, by default
            True

        Returns
        -------
        gpd.GeoDataFrame
            The rivers split dataframe
        """
        if copy:
            return self.__rivers_split.copy()
        else:
            return self.__rivers_split

    def get_river_network(self, copy: bool = True) -> nx.DiGraph:
        """get_river_network returns the river network as a NetworkX graph.

        Parameters
        ----------
        copy: bool, optional
            Whether to return a copy of the network or the original, by default
            True

        Returns
        -------
        nx.Graph | None
            The river network graph if constructed, otherwise None.
        """
        if copy:
            return self.__river_network.copy()
        else:
            return self.__river_network.copy(as_view=True)

    def get_risk_map(self) -> gpd.GeoDataFrame:
        """
        Return the risk map as a GeoDataFrame after constructing it from
        the river network.

        Returns
        -------
        gpd.GeoDataFrame | None
            The risk map GeoDataFrame if constructed, otherwise None.
        """
        self.__construct_risk_map()
        return self.__risk_map

    def get_joined_catchments(
        self, copy: bool = True
    ) -> tuple[gpd.GeoDataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Return the joined catchments, mapping between polygons and river nodes,
        and mapping points.

        Parameters
        ----------
        copy : bool, optional
            Whether to return copies of the dataframes, by default True

        Returns
        -------
        tuple[gpd.GeoDataFrame, pd.DataFrame, pd.DataFrame]
            A tuple containing the joined catchments GeoDataFrame,
            mapping between polygons and river nodes DataFrame, and mapping points DataFrame.
        """
        if (
            self.__joined_catchments is None
            or self.__map_poly_join is None
            or self.__mapping_points is None
        ):
            self.delineate_catchments()
        if copy:
            return (
                self.__joined_catchments.copy(),
                self.__map_poly_join.copy(),
                self.__mapping_points.copy(),
            )
        else:
            return (
                self.__joined_catchments,
                self.__map_poly_join,
                self.__mapping_points,
            )

    # Constructor functions
    def construct_river_graph(self) -> None:
        """
        Construct a river network graph from the processed river data.

        The graph is constructed using the `momepy` library, creating a primal
        graph where each node represents a river segment intersection and
        edges represent river segments.
        """
        self.__river_network = utils.rivers.river_to_graph(self.__rivers_split)

    def delineate_catchments(
        self,
        min_area: float = 20000.0,
    ) -> None:
        """
        Delineate catchments based on the river network and risk map.
        This method uses the `catchment_delineation` utility to delineate
        catchments from the risk map and river network.

        The catchments are stored in the `__joined_catchments` attribute, and
        the mapping between polygons and river nodes is stored in the
        `__map_poly_join` attribute.

        Parameters
        ----------
        min_area : float, optional
            Minimum area(m2) for catchment polygons to be included, by default 20_000.
        """
        logger.info("Delineating catchments...")
        polygons = catchment_delineation.delineate_catchments(
            self.__risk_map,
            pathlib.Path(__file__).parent.joinpath("data", "wbe"),
            pathlib.Path(__file__).parent.joinpath("data", "tiles"),
        )

        polygons["geometry"] = polygons["geometry"].make_valid()
        if self.__catchment_mask is not None:
            if polygons.crs is None:
                raise ValueError(
                    "Polygons have no CRS, cannot clip to catchment mask"
                )
            polygons = gpd.overlay(
                polygons,
                self.__catchment_mask.to_crs(polygons.crs)[["geometry"]],
                how="intersection",
                keep_geom_type=True,
            )

        rmap = (
            self.__risk_map[["geometry"]]
            .reset_index(drop=False)
            .rename(columns={"index": "river_index"})
        )

        polygons["value2"] = polygons["VALUE"] - 1
        polygons["poly"] = polygons.geometry.copy()

        mapping_points = rmap.join(
            polygons[["value2", "poly", "FID"]].set_index("value2"),
            how="left",
            validate="1:1",
        )

        mapping_points["poly"] = mapping_points["poly"].fillna(
            shapely.geometry.Polygon()  # type: ignore
        )
        PM_mapping = mapping_points.copy()

        PM_mapping["area"] = PM_mapping["poly"].area
        PM_mapping["include"] = PM_mapping["area"].fillna(0) > min_area

        map_poly_join = pd.DataFrame(
            columns=["FID_poly", "FID_to_join", "river_index"]
        )

        net: nx.DiGraph = self.__river_network.copy()  # type: ignore
        start_nodes = []
        for node in net.nodes:
            if not len(list(net.successors(node))):
                start_nodes.append(node)

        curr_nodes = start_nodes
        next_nodes = []

        for node in start_nodes:
            c_id = net.nodes[node]["nodeID"]
            c_fid = PM_mapping.loc[c_id, "FID"]
            PM_mapping.loc[c_id, "FID"] = c_fid
            if not pd.isna(c_fid):
                map_poly_join.loc[-1] = (c_fid, c_fid, c_id)
                map_poly_join.index = map_poly_join.index + 1

        while len(curr_nodes):
            for node in curr_nodes:
                c_id = net.nodes[node]["nodeID"]
                c_fid = PM_mapping.loc[c_id, "FID"]
                for p_node in net.predecessors(node):
                    p_id = net.nodes[p_node]["nodeID"]
                    p_fid = PM_mapping.loc[p_id, "FID"]
                    if not PM_mapping.loc[p_id, "include"]:
                        PM_mapping.loc[p_id, "FID"] = c_fid
                        map_poly_join.loc[-1] = (c_fid, p_fid, p_id)
                    else:
                        map_poly_join.loc[-1] = (p_fid, p_fid, p_id)
                    map_poly_join.index = map_poly_join.index + 1
                    next_nodes.append(p_node)
            curr_nodes = next_nodes.copy()
            next_nodes = []

        joining_mapping = map_poly_join[
            map_poly_join["FID_to_join"].notna()
        ].join(
            polygons[["FID", "poly"]].set_index("FID"),
            how="left",
            on="FID_to_join",
            # validate="m:1",
        )
        joining_mapping = joining_mapping[
            joining_mapping["FID_to_join"].notna()
        ]
        joining_mapping["poly"] = joining_mapping["poly"].apply(
            lambda x: shapely.make_valid(x, method="structure")
        )

        joined_catchments: gpd.GeoDataFrame = joining_mapping.groupby(
            "FID_poly"
        ).agg(
            {"poly": shapely.union_all}
        )  # type: ignore
        joined_catchments = joined_catchments.set_geometry("poly").set_crs(
            rmap.crs
        )
        logger.info("Catchments delineated successfully")
        self.__joined_catchments = joined_catchments
        self.__map_poly_join = map_poly_join
        self.__mapping_points = mapping_points
        return

    def catchment_to_river_load(
        self,
        load: gpd.GeoDataFrame,
    ) -> gpd.GeoSeries:
        """
        catchment_to_river_load aggregates the load from catchments to river
        segments based on the mapping between catchments and river nodes.
        This method sums the load for each river segment based on the
        catchment polygons and their associated river indices.

        Parameters
        ----------
        load : gpd.GeoDataFrame
            GeoDataFrame containing the load data with geometry and FID_poly.
            It is neccessary to have a column "FID_poly" that maps the load to
            the river segments and a column "load" that contains the load
            values.

        Returns
        -------
        gpd.GeoSeries
            GeoSeries containing the aggregated load data for river segments.
        """
        fid_load = load.groupby("FID_poly").agg({"load": "sum"})
        river_load = fid_load.join(
            self.__map_poly_join[["river_index", "FID_poly"]].set_index(
                "FID_poly"
            ),
            how="left",
            validate="1:m",
        )
        river_load = river_load.reset_index(drop=False)
        river_load["count"] = river_load.groupby("FID_poly")[
            "FID_poly"
        ].transform("count")

        river_load["load"] /= river_load["count"]
        river_load = river_load[river_load["river_index"].notna()]
        river_load = (
            river_load.drop(columns=["count"])
            .set_index("river_index", verify_integrity=True)
            .sort_index()
        )
        return river_load["load"]

    def __construct_risk_map(self) -> None:
        """
        Convert the river network graph back into a GeoDataFrame.
        """
        if self.__river_network is None:
            raise ValueError("No river network to construct risk map from")
        else:
            self.__risk_map = self.__graph_to_gdf()

    def __graph_to_gdf(self) -> gpd.GeoDataFrame:
        def convert_to_list(x: dict):
            if isinstance(x, dict):
                return list(zip(x.keys(), x.values()))
            elif isinstance(x, set):
                return list(x)
            elif isinstance(x, list):
                return x
            elif pd.isna(x):
                return []
            else:
                return x

        points_data = momepy.nx_to_gdf(
            self.__river_network, points=True, lines=False
        )
        points_data.drop(columns=["x", "y", "nodeID"], inplace=True)
        for col in points_data.columns:
            points_data[col] = points_data[col].apply(convert_to_list)
        return points_data

    # Add points to map
    def add_point_info_to_map(
        self,
        ids: gpd.GeoSeries,
        geometry: gpd.GeoSeries,
        col_name_graph: str,
        max_risk_distance: float,
        max_dist_from_river: float,
        include_upstream: bool = False,
    ) -> gpd.GeoSeries:
        """
        Add information about point locations to the river network graph.

        This method finds the closest points on the river network for given
        geometries and propagates risk information from these points along
        the river network.

        Parameters
        ----------
        ids : gpd.GeoSeries
            IDs of the points to be added.
        geometry : gpd.GeoSeries
            Geometries of the points to be added.
        col_name_graph : str
            Name of the attribute in the graph nodes where the point
            information will be stored.
        max_risk_distance : float
            Maximum distance for risk propagation along the river network.
        max_dist_from_river : float
            Maximum distance for finding the closest river segment to the
            points.
        include_upstream : bool, optional
            Indicates whether to include upstream propagation. Default is
            False.

        Returns
        -------
        gpd.GeoSeries
            GeoSeries of the closest points on the river network.
        """
        if geometry.crs != self.__rivers_split.crs:
            raise ValueError(
                "Points are not in EPSG:27700 CRS which is used by the class"
            )

        closest_point, closest_edge, river_flow = (
            utils.rivers.add_location_on_river_and_closest_edge(
                self.__rivers_split, geometry, max_dist_from_river
            )
        )
        df = pd.DataFrame(
            {
                "ids": ids,
                "closestPoint": closest_point,
                "closestEdge": closest_edge,
            }
        )

        df["idTups"] = list(zip(df["ids"], river_flow))
        df.apply(
            lambda x: graph.add_to_graph(
                self.__river_network,
                col_name_graph,
                x["idTups"],
                x["closestPoint"],
                x["closestEdge"],
                distance_cutoff=max_risk_distance,
                both_ways=include_upstream,
            ),
            axis=1,
        )
        return closest_point

    def add_diffuse_info_to_map(
        self,
        info_col_name: str,
        parameter: str,
        load_method: Callable[
            [Self, str],
            gpd.GeoDataFrame,
        ],
    ) -> None:
        """
        Add diffuse load to the risk map based on the provided load method.

        Parameters
        ----------
        info_col_name : str
            The name of the column in the risk map to store the load values.
        parameter : str
            The parameter to calculate load for, either "P" or "NH4".
        load_method : Callable
            A function that takes in the riskmap and returns a GeoDataFrame of
            load values. It should return a GeoDataFrame with a column "FID_poly"
            that maps the load to the river segments and a column called "load".
        """
        if (
            self.__joined_catchments is None
            or self.__map_poly_join is None
            or self.__mapping_points is None
        ):
            self.delineate_catchments()
        catchment_load = load_method(
            self,
            parameter,
        )
        river_load = self.catchment_to_river_load(catchment_load.copy())
        # Add info to the river network
        netw = self.__river_network
        for node in netw.nodes:
            if netw.nodes[node]["nodeID"] in river_load.index:
                # Ensure the nodeID exists in load before accessing it
                netw.nodes[node][info_col_name] = river_load.loc[
                    netw.nodes[node]["nodeID"],
                ]
            else:
                netw.nodes[node][info_col_name] = 0
        self.__construct_risk_map()
        return

    # Calculate risk from info on map
    def add_point_risk(
        self,
        info_col: str,
        risk_name: str,
        risk_method: Callable,
        distance_scaling: Callable,
        aggregation_method: str = "flow_avg",
        ids_to_ignore: list | None = None,
        inplace: bool = True,
    ) -> gpd.GeoDataFrame | None:
        """
        Add risk information to the risk map about point sources.

        Parameters
        ----------
        info_col : str
            The name of the column in the risk map containing tuples of
            (ID, dist) from river points.
        risk_name : str
            The column name of the risk to be assigned in the risk map.
        risk_method : Callable
            A method from riskID -> float that gives a risk value for each
            point.
        distance_scaling : Callable
            A method from dist -> float which gives the distance scaling of
            that risk.
        aggregation_method : str, optional
            One of ["sum", "avg", "flow_avg"] to aggregate risk values, by
            default "flow_avg".
        ids_to_ignore : list, optional
            The IDs to ignore from the risk calculation, by default [].
        inplace : bool, optional
            Whether to add the risk to the risk map inplace or return a new
            risk map, by default True.

        Returns
        -------
        gpd.GeoDataFrame | None
            The risk values for each point in the risk map if inplace is
            False, otherwise None.

        Raises
        ------
        ValueError
            If the info_col doesn't exist in the risk map.
        """

        risk = graph.add_point_risk(
            self,
            info_col,
            risk_name,
            risk_method,
            distance_scaling,
            aggregation_method,
            ids_to_ignore,
            inplace,
        )
        if inplace:
            return
        else:
            gdf = gpd.GeoDataFrame.from_dict(risk, orient="index")
            gdf = gdf.reset_index()
            gdf.set_geometry(
                gdf.apply(
                    lambda x: shapely.Point(x["level_0"], x["level_1"]), axis=1
                ),
                inplace=True,
            )
            gdf.set_crs(epsg=27700, inplace=True)
            gdf.drop(columns=["level_0", "level_1"], inplace=True)
            return gdf

    def add_diffuse_risk(
        self,
        info_col: str,
        risk_name: str,
        distance_scaling: Callable[[float], float],
        risk_method: Callable[[float], float] = lambda x: x,
        inplace: bool = True,
    ) -> gpd.GeoDataFrame | None:
        """
        add_diffuse_risk adds diffuse risk to the risk map based on the
        provided parameters.

        Parameters
        ----------
        info_col : str
            The name of the column in the risk map containing the load
            information.
        risk_name : str
            The name of the risk column to be added to the risk map.
        distance_scaling : Callable[[float], float]
            A function that scales the load based on distance.
        risk_method : Callable[[float], float], optional
            A function that calculates the risk based on the
            concentration, by default lambda x: x
        inplace : bool, optional
            Whether to add the risk to the risk map inplace or
            return a new risk map, by default True

        Returns
        -------
        gpd.GeoDataFrame | None
            The risk map with the added diffuse risk if inplace is False,
            otherwise None
        """
        risk = graph.add_diffuse_risk(
            self.__river_network,
            info_col,
            risk_name,
            distance_scaling,
            risk_method,
            inplace,
        )
        if inplace:
            return
        else:
            gdf = gpd.GeoDataFrame.from_dict(risk, orient="index")
            gdf = gdf.reset_index()
            gdf.set_geometry(
                gdf.apply(
                    lambda x: shapely.Point(x["level_0"], x["level_1"]), axis=1
                ),
                inplace=True,
            )
            gdf.set_crs(epsg=27700, inplace=True)
            gdf.drop(columns=["level_0", "level_1"], inplace=True)
            return gdf

    def add_simple(
        self, risk_name: str, inplace: bool = True
    ) -> gpd.GeoDataFrame | None:
        """
        add_simple uses a value already present in the risk map

        Parameters
        ----------
        risk_name : str
            The name of the risk column present in the risk map
        inplace : bool, optional
            Whether to return the value or not, by default True
        """
        if inplace:
            return
        else:
            self.__construct_risk_map()
            return self.__risk_map[["geometry", risk_name]].copy()

    def add_risk(self, type: str, **kwargs) -> gpd.GeoDataFrame | None:
        """
        add_risk adds risk to the risk map based on the type of risk and
        parameters provided.

        Parameters
        ----------
        type : str
            The type of risk to add, either "point" or "diffuse". If just columns
            are supposed to be aggregated, the type is "simple".

        Returns
        -------
        gpd.GeoDataFrame | None
            The risk map with the added risk if inplace is False, otherwise None

        Raises
        ------
        ValueError
            If the risk type is not in ["point","diffuse","simple].
        """
        types = ["point", "diffuse", "simple"]
        if type not in types:
            raise ValueError(f"Risk type must be one of {types}, got {type}")
        if type == "point":
            return self.add_point_risk(**kwargs)
        elif type == "diffuse":
            return self.add_diffuse_risk(**kwargs)
        elif type == "simple":
            return self.add_simple(**kwargs)

    def add_all_risk(
        self,
        risk_list: list[dict],
        aggregation_method: Callable = sum,
        risk_name: str = "Risk",
        inplace: bool = True,
    ) -> gpd.GeoDataFrame | None:
        """add_all_risk takes in a list of dictionaries and aggregates the
        risks together
        and adds it to the "Risk" column in the riskmap

        Parameters
        ----------
        risk_list : list[dict]
            A list of dictionaries consisting of parameters for the
            RiskMap.add_risk() method

            type: str

            info_col: str (optional)

            risk_name: str

            risk_method: Callable (optional)

            distance_scaling: Callable (optional)

            aggregation_method: str (optional)

            ids_to_ignore: list (optional)


        aggregation_method : Callable, optional
            The aggregation method for all the risks together list[float]
            -> float, by default sum
        risk_name : str, optional
            The name of the risk column to be added to the risk map, by default
            "Risk"
        inplace : bool, optional
            Whether to add the risk to the risk map inplace or return a new
            risk map, by default True

        Returns
        -------

        gpd.GeoDataFrame | None
            The risk map with the aggregated risk if inplace is False,
            otherwise None

        Raises
        ------
        ValueError
            If one of the risk_name is "Risk"
        """
        if not inplace:
            risks = gpd.GeoDataFrame({"geometry": []}, geometry="geometry")
        for item in risk_list:
            if item["risk_name"] == "Risk":
                raise ValueError("Cannot have the risk name be Risk")
            if inplace:
                self.add_risk(**item)
            else:
                risks = (
                    risks.set_index("geometry")
                    .join(
                        self.add_risk(**item, inplace=False).set_index(
                            "geometry"
                        ),
                        how="outer",
                    )
                    .reset_index()
                )

        if inplace:
            for node in self.__river_network.nodes:
                self.__river_network.nodes[node][risk_name] = (
                    aggregation_method(
                        [
                            self.__river_network.nodes[node][item["risk_name"]]
                            for item in risk_list
                        ]
                    )
                )
            return
        else:
            risks[risk_name] = risks.apply(
                lambda x: aggregation_method(
                    [x[item["risk_name"]] for item in risk_list]
                ),
                axis=1,
            )
            return gpd.GeoDataFrame(
                risks, geometry="geometry", crs="EPSG:27700"
            )
