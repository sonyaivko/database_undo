"""
turns a FD list into:
  - a NetworkX DiGraph (nodes = columns, edges = "determines")
  - column_rules: {col: (lhs_cols, avg_group_size)} 
  - a topological order for reconstruction

Multiple FDs can determine the same RHS column. Pick one rule per column:
the one with the highest avg_group_size.

"""
import networkx as nx


def build_dependency_graph(usable_fds):
    best_rule = {}  # rhs_col -> (lhs_cols, avg_group_size)
    for lhs, rhs, ags in usable_fds:
        if rhs not in best_rule or ags > best_rule[rhs][1]:
            best_rule[rhs] = (lhs, ags)

    g = nx.DiGraph()
    g.add_nodes_from(best_rule.keys())
    for rhs, (lhs, ags) in best_rule.items():
        for l in lhs:
            g.add_node(l)
            g.add_edge(l, rhs, avg_group_size=ags)

    # Break cycles by removing the WEAKEST rule involved
    while True:
        try:
            cycle = nx.find_cycle(g)
        except nx.NetworkXNoCycle:
            break
        rhs_in_cycle = set(v for _u, v in cycle)
        # drop whichever rule touching this cycle is weakest (lowest avg group size) 
        # keeps the strongest derivations, sheds the least
        weakest_rhs = min(rhs_in_cycle, key=lambda n: best_rule[n][1] if n in best_rule else -1)
        if weakest_rhs in best_rule:
            lhs, _ags = best_rule[weakest_rhs]
            for l in lhs:
                if g.has_edge(l, weakest_rhs):
                    g.remove_edge(l, weakest_rhs)
            del best_rule[weakest_rhs]
        else:
            # shouldn't normally happen, but avoid an infinite loop if it does
            u, v = cycle[0]
            g.remove_edge(u, v)

    topo_order = list(nx.topological_sort(g))
    return g, best_rule, topo_order