"""Stack test runner: AP2 + MCP + FastAPI in one project. Three parts, each a real round trip.

A. MCP over stdio, server in its own process (how Claude Desktop would launch it).
B. FastAPI under uvicorn in another process, reading what A wrote and signing a human approval.
C. MCP over HTTP, mounted inside the FastAPI process (what a remote connector would call).
"""
import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parent
STATE = APP.parent / "state"
shutil.rmtree(STATE, ignore_errors=True)
os.environ["STACK_TEST_STATE"] = str(STATE)
ENV = {"STACK_TEST_STATE": str(STATE), "PATH": os.environ["PATH"]}

import core  # noqa: E402  (needs STACK_TEST_STATE)
from mcp import Client  # noqa: E402
from mcp.client.stdio import StdioServerParameters  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append(ok)
    print(f"{'PASS' if ok else 'FAIL'} | {name}{' | ' + str(detail) if detail else ''}")


def data(result):
    """The dict a tool returned, whatever shape this SDK version wraps it in."""
    structured = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    if structured:
        return structured.get("result", structured)
    return json.loads(result.content[0].text)


def http(method, url):
    with urllib.request.urlopen(urllib.request.Request(url, method=method), timeout=10) as response:
        return json.loads(response.read())


async def buy(client, quantity):
    quote = data(await client.call_tool("get_quote", {"sku": "464306", "quantity": quantity}))
    started = time.perf_counter()
    order = data(await client.call_tool("place_order", {"quote_id": quote["quote_id"]}))
    return quote, order, (time.perf_counter() - started) * 1000


async def main():
    core.setup()

    print("A. MCP over stdio, server in its own process")
    async with Client(StdioServerParameters(command=sys.executable, args=[str(APP / "mcp_server.py")], env=ENV, cwd=str(APP))) as client:
        tools = [tool.name for tool in (await client.list_tools()).tools]
        check("tools listed", tools == ["get_quote", "place_order"], tools)
        quote, order, ms = await buy(client, 1000)
        check("1 000 L (1 010 EUR) ordered by the agent alone", order["status"] == "accepted", f"{order} in {ms:.0f} ms")
        big_quote, big_order, _ = await buy(client, 2000)
        check("2 000 L (2 020 EUR) stopped for a human", big_order["status"] == "needs_human", big_order)

    print("B. FastAPI under uvicorn, another process")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    web = subprocess.Popen([sys.executable, "-m", "uvicorn", "web:web", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
                           cwd=APP, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for _ in range(50):
            try:
                log = http("GET", base + "/audit")
                break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("uvicorn did not start")
        check("web process reads the 2 decisions written by the MCP process", [line["event"] for line in log] == ["accepted", "needs_human"], [line["event"] for line in log])
        approval = http("POST", f"{base}/approve/{big_quote['quote_id']}")
        check("human approval signed with the manager's key", approval["status"] == "accepted", approval)

        print("C. MCP over HTTP, inside the FastAPI process")
        async with Client(f"{base}/agent/mcp") as client:
            tools = [tool.name for tool in (await client.list_tools()).tools]
            check("tools listed over HTTP", tools == ["get_quote", "place_order"], tools)
            _, order, ms = await buy(client, 500)
            check("500 L ordered over HTTP", order["status"] == "accepted", f"{order['status']} in {ms:.0f} ms")
        log = http("GET", base + "/audit")
        check("audit log holds all 4 decisions from 2 processes", len(log) == 4 and len({line["pid"] for line in log}) == 2,
              [(line["event"], line.get("signed_by", "-"), line["pid"]) for line in log])
    finally:
        web.terminate()
        output = web.communicate(timeout=10)[0].strip()
        if output:
            print("uvicorn output:\n" + output[-1500:])

    print(f"\n{sum(checks)}/{len(checks)} checks pass")


asyncio.run(main())
