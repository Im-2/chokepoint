"""MCP server: the same nine tools as tools.py, exposed over stateless streamable HTTP.

The wrappers are thin on purpose: they only give MCP the typed argument schema and forward to
tools.py, so REST, MCP and the agent all run exactly the same code.

Note: MCP Python SDK 2.x renamed FastMCP to MCPServer.
"""
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from app import tools


def build_server(graph_name: str | None = None) -> MCPServer:
    """A server bound to one graph (default: the tenant graph). Tests pass a 'test:' graph."""
    mcp = MCPServer("chokepoint")
    g = graph_name

    def describe(name):
        return tools.TOOLS[name][1]

    @mcp.tool(description=describe("find_attack_paths"))
    def find_attack_paths(depth: int = 8, limit: int = 50) -> dict[str, Any]:
        return tools.find_attack_paths(depth, limit, graph_name=g)

    @mcp.tool(description=describe("explain_reachability"))
    def explain_reachability(from_name: str, to_name: str | None = None) -> dict[str, Any]:
        return tools.explain_reachability(from_name, to_name, graph_name=g)

    @mcp.tool(description=describe("rank_choke_edges"))
    def rank_choke_edges(depth: int = 8, limit: int = 15) -> dict[str, Any]:
        return tools.rank_choke_edges(depth, limit, graph_name=g)

    @mcp.tool(description=describe("rank_load_bearing_assets"))
    def rank_load_bearing_assets(limit: int = 20) -> dict[str, Any]:
        return tools.rank_load_bearing_assets(limit, graph_name=g)

    @mcp.tool(description=describe("plan_remediation"))
    def plan_remediation(budget: int = 3) -> dict[str, Any]:
        return tools.plan_remediation(budget, graph_name=g)

    @mcp.tool(description=describe("simulate_fix"))
    def simulate_fix(edge_ids: list[str]) -> dict[str, Any]:
        return tools.simulate_fix(edge_ids, graph_name=g)

    @mcp.tool(description=describe("propose_change"))
    def propose_change(edge_ids: list[str], plan_note: str | None = None) -> dict[str, Any]:
        return tools.propose_change(edge_ids, plan_note, graph_name=g)

    @mcp.tool(description=describe("record_decision"))
    def record_decision(decision_id: str, action: str, reason: str | None = None) -> dict[str, Any]:
        return tools.record_decision(decision_id, action, reason, graph_name=g)

    @mcp.tool(description=describe("recall_decisions"))
    def recall_decisions(asset_name: str | None = None) -> dict[str, Any]:
        return tools.recall_decisions(asset_name, graph_name=g)

    return mcp


# The production server + its ASGI app, mounted at /mcp by app/main.py.
# stateless_http: every request is independent (no session ids), which is what serverless needs.
mcp_server = build_server()
# DNS-rebinding protection guards servers on a developer's localhost from browser attacks; this is a
# public API on a real hostname with no cookies or ambient credentials, and the SDK would answer
# 421 to every hostname it does not know, so it is switched off explicitly.
mcp_asgi_app = mcp_server.streamable_http_app(
    json_response=True, stateless_http=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
