"""Greedy remediation planner. Pure Python over results the graph already produced.

The graph does the hard part (enumerating every attack path). This file only answers:
"which few edges should we remove so the most paths are cut for the least disruption?"
That is weighted set cover, which is NP-hard, so we use the standard greedy heuristic.
It is NOT provably optimal and we say so wherever we show a plan.
"""


def greedy_plan(paths, edge_info, budget, excluded=frozenset()):
    """paths:     list of lists of edge ids (one list per attack path)
    edge_info: {edge_id: {"disruption": int, ...}} for every edge that appears on a path
    budget:    maximum number of edges to pick
    excluded:  edge ids we must not pick (rejected by a human in the past)

    Returns (steps, remaining_paths, note). Each step is
    {"edge_id", "paths_cut", "disruption"} where paths_cut counts only the paths that
    were still alive when the edge was picked.

    Rules: pick the edge with the best (newly cut paths / disruption); never pick an edge
    that cuts nothing; stop as soon as no paths remain.
    """
    remaining = [set(p) for p in paths]
    steps = []
    chosen = set()

    while remaining and len(steps) < budget:
        best = None  # (score, newly_cut, -disruption, edge_id)
        for edge_id, info in edge_info.items():
            if edge_id in excluded or edge_id in chosen:
                continue
            newly_cut = sum(1 for p in remaining if edge_id in p)
            if newly_cut == 0:
                continue  # an edge that cuts nothing is never worth picking
            candidate = (newly_cut / info["disruption"], newly_cut, -info["disruption"], edge_id)
            # compare on score, then more paths cut, then lower disruption, then id (stable)
            if best is None or candidate[:3] > best[:3] or (candidate[:3] == best[:3] and edge_id < best[3]):
                best = candidate
        if best is None:
            break  # nothing allowed cuts any remaining path
        _, newly_cut, neg_disruption, edge_id = best
        steps.append({"edge_id": edge_id, "paths_cut": newly_cut, "disruption": -neg_disruption})
        chosen.add(edge_id)
        remaining = [p for p in remaining if edge_id not in p]

    if not remaining:
        used = len(steps)
        note = (f"All {len(paths)} attack paths are cut using {used} of {budget} allowed edge(s)."
                if used < budget else f"All {len(paths)} attack paths are cut using the full budget of {budget}.")
    elif len(steps) == budget:
        note = (f"Budget of {budget} used up; {len(remaining)} of {len(paths)} paths remain. "
                "A larger budget may cut them.")
    else:
        note = (f"Stopped after {len(steps)} of {budget} edge(s): no remaining edge that is allowed "
                f"(not rejected earlier) cuts any of the {len(remaining)} paths left.")
    note += " Greedy heuristic, not provably optimal."
    return steps, [sorted(p) for p in remaining], note
