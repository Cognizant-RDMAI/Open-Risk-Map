from collections import defaultdict
from collections.abc import Callable

import networkx as nx
import numpy as np
import shapely


def add_to_graph(
    graph: nx.DiGraph,
    field_name: str,
    id: int | str | tuple[str, float],
    p: shapely.Point,
    edge: tuple,
    distance_cutoff: float,
    both_ways: bool = True,
    is_node: bool = False,
) -> None:
    """
    Add points and their distances from nodes to the graph.

    This function performs a BFS to add distance information to the graph's
    nodes.

    Parameters
    ----------
    graph : nx.DiGraph
        The graph to update with distance information.
    field_name : str
        The field in the node attributes to store the information.
    id : int, str, or tuple[str, float]
        The identifier of the point and the flow at the point.
    p : shapely.Point
        A point object representing the location of the point.
    edge : tuple
        The edge corresponding to the point in the graph.
    distance_cutoff : float
        The maximum distance for BFS traversal.
    both_ways : bool, optional
        Whether to traverse both upstream and downstream.
        Default is True.
    is_node : bool, optional
        Whether the point is a node in the graph. Default is False.
    """
    if (edge is None or p is None) and not is_node:
        return

    if is_node:
        next_node = (p.x, p.y)
        next_dist = 0
    else:
        # Loop over successors, add data
        next_node = edge[1]
        # Find distance between geometry and first point
        next_dist = p.distance(shapely.Point(next_node))

    # Check if distance lesser than threshold
    if next_dist < distance_cutoff:
        # Get prev data
        data_before = graph.nodes[next_node].get(field_name)
        # If exists, add data
        if data_before is not None and isinstance(data_before, dict):
            data_before[id] = next_dist
        # If doesn't exist, add new dict
        else:
            nx.set_node_attributes(
                graph, {next_node: {id: next_dist}}, field_name
            )

        # Loop over children nodes
        directed_graph_bfs(
            graph, next_node, field_name, distance_cutoff, id, True
        )

    if not both_ways:
        return

    # Loop over predecessors
    if is_node:
        prev_node = (p.x, p.y)
        prev_dist = 0
    else:
        prev_node = edge[0]
        prev_dist = -p.distance(shapely.Point(prev_node))
    if prev_dist > -distance_cutoff:
        data_before = graph.nodes[prev_node].get(field_name)
        if data_before is not None and isinstance(data_before, dict):
            data_before[id] = prev_dist
        else:
            nx.set_node_attributes(
                graph, {prev_node: {id: prev_dist}}, field_name
            )
        directed_graph_bfs(
            graph, prev_node, field_name, distance_cutoff, id, False
        )
    return


def directed_graph_bfs(
    graph: nx.DiGraph,
    start_node: tuple,
    col_name: str,
    distance_cutoff: float,
    id: int | str | tuple[str, float],
    along_direction: bool = True,
) -> None:
    """
    Perform BFS on a directed graph to propagate risk information.

    Parameters
    ----------
    graph : nx.DiGraph
        The directed graph representing the river network.
    start_node : tuple
        The starting node for the BFS.
    col_name : str
        The attribute in the graph nodes where risk information is stored.
    distance_cutoff : float
        Maximum distance for risk propagation.
    id : int or str or tuple[str, float]
        Identifier for the point location.
    along_direction : bool, optional
        Whether to propagate risk along the graph's direction. Default is True.
    """
    curr_nodes = [start_node]

    while len(curr_nodes) > 0:
        new_curr = []
        for node in curr_nodes:
            # Check children
            if along_direction:
                children = graph.successors(node)
            else:
                children = graph.predecessors(node)

            for child in children:
                # Check if already added
                data_before = graph.nodes[child].get(col_name)
                if data_before is not None and id in data_before:
                    continue

                # Check distance
                if along_direction:
                    total_dist = (
                        graph.nodes[node][col_name][id]
                        + graph[node][child]["mm_len"]
                    )
                else:
                    total_dist = (
                        graph.nodes[node][col_name][id]
                        - graph[child][node]["mm_len"]
                    )

                if (
                    total_dist >= distance_cutoff
                    or total_dist <= -distance_cutoff
                ):
                    continue

                # Add data
                if data_before is not None and isinstance(data_before, dict):
                    data_before[id] = total_dist
                    nx.set_node_attributes(
                        graph, {child: data_before}, col_name
                    )

                # If doesn't exist, add new dict
                else:
                    nx.set_node_attributes(
                        graph, {child: {id: total_dist}}, col_name
                    )

                # Add to new_curr
                new_curr.append(child)
        curr_nodes = new_curr
    return


def add_point_risk(
    riskmap,
    info_col: str,
    risk_name: str,
    risk_method: Callable,
    distance_scaling: Callable,
    aggregation_method: str = "flow_avg",
    ids_to_ignore: list | None = None,
    inplace=True,
) -> dict[tuple, dict[str, float]] | None:
    """
    Add point risk information to a riskmap containing a river graph.

    Parameters
    ----------
    riskmap : RiskMap
        The riskmap to update with risk information.
    info_col : str
        The name of the info column associated with the risk.
    risk_name : str
        The name of the risk to store in the output.
    risk_method : Callable
        Function to calculate risk given an ID and river flow.
    distance_scaling : Callable
        Function to scale the risk based on distance.
    aggregation_method : str, optional
        Method to aggregate risks. Default is "flow_avg".
    ids_to_ignore : list, optional
        IDs to ignore while calculating the risk. Default is [].
    inplace : bool, optional
        Whether to update the graph in place or return a risk dictionary.
        Default is True.

    Returns
    -------
    dict[dict[float]] or None
        A dictionary of risk values if `inplace` is False, otherwise None.

    Raises
    ------
    NotImplementedError
        If the aggregation method is not implemented.
    ValueError
        If the info column is not present in the graph.
    """
    network: nx.DiGraph = riskmap.get_river_network(copy=False)
    found = False
    if not inplace:
        retdict: dict[tuple, dict[str, float]] = defaultdict(dict)

    for node in network.nodes:
        rsk = []
        weights = []
        if info_col in network.nodes[node]:
            found = True
            for id, dist in network.nodes[node][info_col].items():
                if (ids_to_ignore is not None) and (id[0] in ids_to_ignore):
                    continue
                river_flow = id[1]
                idrisk = risk_method(id[0], river_flow)
                if idrisk:
                    rsk.append(idrisk * distance_scaling(dist))
                    weights.append(river_flow)

        if aggregation_method == "sum":
            agg_risk = np.sum(rsk)
        elif aggregation_method == "avg":
            if not len(rsk):
                agg_risk = 0
            else:
                agg_risk = np.mean(rsk)
        elif aggregation_method == "flow_avg":
            flow_node = network.nodes[node].get("flow", 0)
            agg_risk = sum([w * r for w, r in zip(weights, rsk)]) / flow_node
        else:
            raise NotImplementedError(
                "aggregation_method not in ['sum','avg','flow_avg']"
            )

        if inplace:
            network.nodes[node][risk_name] = agg_risk
        else:
            retdict[node][risk_name] = agg_risk

    if not found:
        raise ValueError(f"Column {info_col} not found in network nodes")

    if not inplace:
        return retdict
    return


def add_diffuse_risk(
    netw: nx.DiGraph,
    info_col: str,
    risk_name: str,
    distance_scaling: Callable[[float], float] = lambda x: x,
    risk_method: Callable[[float], float] = lambda x: x,
    inplace: bool = True,
) -> dict[tuple, dict[str, float]] | None:

    netw2: nx.DiGraph = netw.copy()

    for node in netw2.nodes:
        # Add column about number left for calculation to finish
        netw2.nodes[node]["n_pred_left"] = len(list(netw2.predecessors(node)))

    found = False
    if not inplace:
        retdict: dict[tuple, dict[str, float]] = defaultdict(dict)

    curr_nodes = set()
    for node in netw.nodes:
        if not len(list(netw.predecessors(node))):
            curr_nodes.add(node)

    while len(curr_nodes):
        next_nodes = set()

        for node in curr_nodes:
            if not found and info_col in netw.nodes[node]:
                found = True

            # If there are predecessors left, skip this node
            if netw2.nodes[node]["n_pred_left"] > 0:
                next_nodes.add(node)
                continue

            r_load = netw.nodes[node].get(info_col, 0)
            rflow = netw.nodes[node].get("flow", 0)

            # Calculate risk
            cum = r_load
            for parent in netw2.predecessors(node):
                cum += netw2.nodes[parent][
                    info_col + "_cum"
                ] * distance_scaling(netw2[parent][node]["mm_len"])
            netw2.nodes[node][info_col + "_cum"] = cum

            if rflow != 0:
                risk = risk_method(cum / rflow)
            else:
                risk = 0

            if inplace:
                netw.nodes[node][risk_name] = risk
            else:
                retdict[node][risk_name] = risk

            # Update successors
            for child in netw2.successors(node):
                netw2.nodes[child]["n_pred_left"] -= 1
                next_nodes.add(child)
            # Remove from next if present
            next_nodes.discard(node)

        curr_nodes = next_nodes

    if not found:
        raise ValueError(f"Column {info_col} not found in network nodes")
    if not inplace:
        return retdict
    return
