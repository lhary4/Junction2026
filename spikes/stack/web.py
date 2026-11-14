"""Stack test: the web page's API (FastAPI), with the same MCP server also mounted over HTTP in this process."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

import core
from mcp_server import server

mcp_app = server.streamable_http_app()  # creates the session manager used in the lifespan below


@asynccontextmanager
async def lifespan(_app):
    async with server.session_manager.run():
        yield


web = FastAPI(lifespan=lifespan)


@web.get("/audit")
def audit():
    return core.read_audit()


@web.post("/approve/{quote_id}")
def approve(quote_id: str):
    return core.approve(quote_id)


web.mount("/agent", mcp_app)  # MCP endpoint: /agent/mcp
