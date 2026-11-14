"""Stack test: the MCP door on top of core.py. mcp 2.x renamed FastMCP to MCPServer."""
from mcp.server.mcpserver import MCPServer

import core

server = MCPServer("valio-aimo-stack-test")


@server.tool()
def get_quote(sku: str, quantity: int) -> dict:
    """Get a signed quote for a product code and a quantity in sales units."""
    return core.get_quote(sku, quantity)


@server.tool()
def place_order(quote_id: str) -> dict:
    """Place the order for a quote. Returns accepted, refused, or needs_human."""
    return core.place_order(quote_id)


if __name__ == "__main__":
    server.run("stdio")
