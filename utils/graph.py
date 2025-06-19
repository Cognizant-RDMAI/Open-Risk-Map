from collections import defaultdict
from collections.abc import Callable

import networkx as nx
import numpy as np
import shapely


def add_to_graph(
    graph: nx.DiGraph,
    field_name: str,
    id: int | str | tuple[str, str],
    p: shapely.Point,
    edge: tuple,
    distance_cutoff: float,
    directed: bool,
    both_ways: bool = True,
    is_node: bool = False,
) -> None:
    """
    Add points and their distances from nodes to the graph.

    This function performs a BFS to add distance information to the graph's
    nodes. It works for both directed and undirected graphs.

    Parameters
    ----------
    graph : nx.DiGraph
        The graph to update with distance information.
    field_name : str
        The field in the node attributes to store the information.
    id : int, str, or tuple[str, str]
        The identifier of the point.
    p : shapely.Point
        A point object representing the location of the point.
    edge : tuple
        The edge corresponding to the point in the graph.
    distance_cutoff : float
        The maximum distance for BFS traversal.
    directed : bool
        Whether the graph is directed.
    both_ways : bool, optional
        For directed graphs, whether to traverse both upstream and downstream.
        Default is True.
    is_node : bool, optional
        Whether the point is a node in the graph. Default is False.
    """
    if (edge is None or p is None) and not is_node:
        return

    if directed:
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
            data_before = graph.nodes(data=field_name)[next_node]
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
            data_before = graph.nodes(data=field_name)[prev_node]
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

    else:
        traversed = set()

        curr_nodes = []
        if is_node:
            next_node = (p.x, p.y)
            next_dist = 0
        else:
            next_node = edge[1]
            next_dist = p.distance(shapely.Point(next_node))
        # Check if distance lesser than threshold
        if next_dist < distance_cutoff:
            # Get prev data
            data_before = graph.nodes(data=field_name)[next_node]
            # If exists, add data
            if data_before is not None and isinstance(data_before, dict):
                data_before[id] = next_dist
            # If doesn't exist, add new dict
            else:
                nx.set_node_attributes(
                    graph, {next_node: {id: next_dist}}, field_name
                )
            curr_nodes.append(next_node)
            traversed.add(next_node)
        prev_node = edge[0]
        prev_dist = p.distance(shapely.Point(prev_node))
        if prev_dist < distance_cutoff:
            data_before = graph.nodes(data=field_name)[prev_node]
            if data_before is not None and isinstance(data_before, dict):
                data_before[id] = prev_dist
            else:
                nx.set_node_attributes(
                    graph, {prev_node: {id: prev_dist}}, field_name
                )
            curr_nodes.append(prev_node)
            traversed.add(prev_node)
        curr_nodes = directed_graph_bfs(
            graph, curr_nodes, field_name, distance_cutoff, id, traversed
        )
        return


def directed_graph_bfs(
    graph: nx.DiGraph,
    start_node: tuple,
    col_name: str,
    distance_cutoff: float,
    id: int | str,
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
    id : int or str
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
                data_before = graph.nodes(data=col_name)[child]
                if data_before is not None and id in data_before:
                    continue

                # Check distance
                if along_direction:
                    total_dist = (
                        graph.nodes(data=col_name)[node][id]
                        + graph[node][child]["mm_len"]
                    )
                else:
                    total_dist = (
                        graph.nodes(data=col_name)[node][id]
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


def undirected_graph_bfs(
    graph: nx.Graph,
    current_nodes: list[tuple],
    col_name: str,
    distance_cutoff: float,
    id: int | str,
    traversed: set[tuple],
) -> list[tuple]:
    """
    Perform BFS on an undirected graph to propagate risk information.

    Parameters
    ----------
    graph : nx.Graph
        The undirected graph representing the river network.
    current_nodes : list[tuple]
        List of current nodes to process.
    col_name : str
        The attribute in the graph nodes where risk information is stored.
    distance_cutoff : float
        Maximum distance for risk propagation.
    id : int or str
        Identifier for the point location.
    traversed : set[tuple]
        Set of nodes that have already been processed.

    Returns
    -------
    list[tuple]
        List of nodes processed in the current BFS iteration.
    """
    while len(current_nodes) > 0:
        new_current_nodes = []
        for node in current_nodes:
            children = [c for c in graph.neighbors(node) if c not in traversed]
            for child in children:
                data_before = graph.nodes(data=col_name)[child]
                if data_before is not None and id in data_before:
                    continue

                # Check distance
                total_dist = (
                    graph.nodes(data=col_name)[node][id]
                    + graph[node][child]["mm_len"]
                )

                if total_dist >= distance_cutoff:
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
                traversed.add(child)
                new_current_nodes.append(child)
        current_nodes = new_current_nodes
    return


def add_risk(
    riskmap,
    info_col: str,
    risk_name: str,
    risk_method: Callable,
    distance_scaling: Callable,
    aggregation_method: str = "w_avg",
    ids_to_ignore: list | None = None,
    inplace=True,
) -> dict[dict[float]] | None:
    """
    Add risk information to a riskmap containing a river graph.

    Parameters
    ----------
    riskmap : RiskMap
        The riskmap to update with risk information.
    info_col : str
        The name of the info column associated with the risk.
    risk_name : str
        The name of the risk to store in the output.
    risk_method : Callable
        Function to calculate risk given an ID.
    distance_scaling : Callable
        Function to scale the risk based on distance.
    aggregation_method : str, optional
        Method to aggregate risks. Default is "w_avg".
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
    network = riskmap.get_river_network(copy=False)
    rivers = riskmap.get_rivers(copy=False)
    found = False
    if not inplace:
        retdict: dict[dict[float]] = defaultdict(dict)

    for node in network.nodes:
        rsk = []
        weights = []
        if info_col in network.nodes[node]:
            found = True
            for id, dist in network.nodes[node][info_col].items():
                if (ids_to_ignore is not None) and (id[0] in ids_to_ignore):
                    continue
                river_info = rivers.loc[id[1]].to_dict()
                idrisk = risk_method(id[0], river_info)
                if idrisk:
                    rsk.append(idrisk * distance_scaling(dist))
                    weights.append(river_info["US_Accum"])

        if aggregation_method == "sum":
            agg_risk = np.sum(rsk)
        elif aggregation_method == "avg":
            if not len(rsk):
                agg_risk = 0
            else:
                agg_risk = np.mean(rsk)
        elif aggregation_method == "w_avg":
            river_ids = list(network.nodes[node]["riverID"])
            accum_len_node = rivers.loc[river_ids, "US_Accum"].max()
            agg_risk = (
                sum([w * r for w, r in zip(weights, rsk)]) / accum_len_node
            )
        else:
            raise NotImplementedError(
                "aggregation_method not in ['sum','avg','w_avg']"
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


def integrate_field(
    graph: nx.DiGraph, field: str, output_name: str = None
) -> None:
    """
    Integrate a field on the nodes over the edges of the graph.

    Parameters
    ----------
    graph : nx.DiGraph
        Graph with the field values present on every node.
    field : str
        The key name of the field to integrate.
    output_name : str, optional
        The name of the output field on the edges. Default is `field + "_int"`.
    """
    if output_name is None:
        output_name = field + "_int"
    for node in graph.nodes:
        for child in graph.successors(node):
            graph[node][child][output_name] = (
                (
                    graph.nodes[child].get(field, 0)
                    + graph.nodes[node].get(field, 0)
                )
                / 2
                * graph[node][child]["mm_len"]
            )
    return


def integrate_nn_field_product(
    graph: nx.DiGraph, field1: str, field2: str, output_name: str = None
) -> None:
    """
    Integrate the product of two fields defined on the graph nodes.

    Parameters
    ----------
    graph : nx.DiGraph
        Graph with the field values present on every node.
    field1 : str
        The key name of the first field.
    field2 : str
        The key name of the second field.
    output_name : str, optional
        The name of the output field on the edges. Default is
        `field1 + "_" + field2 + "_int"`.
    """
    if output_name is None:
        output_name = field1 + "_" + field2 + "_int"
    for node in graph.nodes:
        for child in graph.successors(node):
            f1, f2 = (graph.nodes[child].get(field1, 0),)
            graph.nodes[node].get(field1, 0)
            g1, g2 = (graph.nodes[child].get(field2, 0),)
            graph.nodes[node].get(field2, 0)
            graph[node][child][output_name] = (
                f1 * g1 / 3 + f1 * g2 / 6 + f2 * g1 / 6 + f2 * g2 / 3
            ) * graph[node][child]["mm_len"]
    return


def integrate_ne_field_product(
    graph: nx.DiGraph, n_field: str, e_field: str, output_name: str = None
) -> None:
    """
    Integrate the product of a node field and an edge field over the graph.

    Parameters
    ----------
    graph : nx.DiGraph
        The graph in question.
    n_field : str
        The name of the field on the nodes.
    e_field : str
        The name of the field on the edges.
    output_name : str, optional
        The name of the output field on the edges. Default is
        `n_field + "_" + e_field + "_int"`.
    """
    if output_name is None:
        output_name = n_field + "_" + e_field + "_int"
    for node in graph.nodes:
        for child in graph.successors(node):
            graph[node][child][output_name] = (
                graph[node][child][e_field]
                * (
                    graph.nodes[node].get(n_field, 0)
                    + graph.nodes[child].get(n_field, 0)
                )
                * graph[node][child]["mm_len"]
                / 2
            )
    return


def difference_field(
    graph: nx.DiGraph, field: str, output_name: str = None
) -> None:
    """
    Compute the difference of a field on the nodes and store it.

    Parameters
    ----------
    graph : nx.DiGraph
        The directed graph.
    field : str
        The name of the field.
    output_name : str, optional
        The name of the output field. Default is `field + "_diff"`.
    """
    if output_name is None:
        output_name = field + "_diff"
    for node in graph.nodes:
        diff = []
        for _i, parent in enumerate(graph.predecessors(node)):
            diff.append(
                (
                    graph.nodes[node].get(field, 0)
                    - graph.nodes[parent].get(field, 0)
                )
            )
        diff = np.array(diff)
        if not len(diff):
            difference = 0
        elif (diff < 0).any():
            difference = np.mean(diff[diff < 0])
        else:
            difference = np.mean(diff)
        graph.nodes[node][output_name] = difference
    return


def func_field_e(
    graph: nx.DiGraph, func: Callable, field: str, output_name: str = None
) -> None:
    """
    Apply a function to a field on the edges and store the result.

    Parameters
    ----------
    graph : nx.DiGraph
        The directed graph.
    func : Callable
        The function to apply to the field.
    field : str
        The name of the field on the edges.
    output_name : str, optional
        The name of the output field. Default is `field + "_abs"`.
    """
    if output_name is None:
        output_name = field + "_abs"
    for edge in graph.edges:
        graph[edge[0]][edge[1]][output_name] = func(
            graph[edge[0]][edge[1]].get(field, 0)
        )
    return


def func_field_n(
    graph: nx.DiGraph, func: Callable, field: str, output_name: str = None
) -> None:
    """
    Apply a function to a field on the nodes and store the result.

    Parameters
    ----------
    graph : nx.DiGraph
        The directed graph.
    func : Callable
        The function to apply to the field.
    field : str
        The name of the field on the nodes.
    output_name : str, optional
        The name of the output field. Default is `field + "_abs"`.
    """
    if output_name is None:
        output_name = field + "_abs"
    for node in graph.nodes:
        graph.nodes[node][output_name] = func(graph.nodes[node].get(field, 0))
    return
