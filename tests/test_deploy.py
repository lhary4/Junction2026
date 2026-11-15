"""deploy/: the hosted demo. The page, the proxy block and the unit files must agree on names and ports."""

import re
from pathlib import Path

from agent_mcp import server as mcp_server
from scripts import dev

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "deploy"
PORTS = {name: port for name, _, port in dev.SERVICES}
PAGE_SERVICES = ("driver", "harness", "assistant")  # the three the page calls from the browser


def read(name: str) -> str:
    return (DEPLOY / name).read_text(encoding="utf-8")


def test_the_proxy_sends_each_prefix_of_the_page_to_the_port_of_that_service():
    script = (ROOT / "surface" / "static" / "portal.js").read_text(encoding="utf-8")
    proxy = read("Caddyfile.snippet")
    for name in PAGE_SERVICES:
        assert f'serviceUrl("{name}", {PORTS[name]})' in script
        block = re.search(rf"handle /{name}/\* \{{(.*?)\}}", proxy, re.DOTALL)
        assert block, f"no block for /{name}/ in the proxy"
        assert f"uri strip_prefix /{name}" in block.group(1)
        assert f"reverse_proxy 172.18.0.1:{PORTS[name]}" in block.group(1)


def test_the_gateway_is_never_public():
    assert f":{PORTS['gateway']}" not in read("Caddyfile.snippet")
    assert f"junction-bridge@{PORTS['gateway']}.socket" not in read("junction-demo.service")


def test_the_mcp_server_is_only_reachable_under_the_secret_path():
    proxy = read("Caddyfile.snippet")
    assert "@mcp path /mcp-<token> /mcp-<token>/" in proxy  # the real token is never in the repo
    assert f"reverse_proxy 172.18.0.1:{mcp_server.HTTP_PORT}" in proxy
    assert proxy.index("handle @mcp") < proxy.index("handle /mcp*")  # the secret path first, then the 404
    assert re.search(r"handle /mcp\* \{\s*respond 404\s*\}", proxy)


def test_every_port_the_proxy_calls_has_its_relay():
    wanted = read("junction-demo.service")
    for port in set(re.findall(r"reverse_proxy 172\.18\.0\.1:(\d+)", read("Caddyfile.snippet"))):
        assert f"junction-bridge@{port}.socket" in wanted


def test_the_mcp_unit_answers_to_the_host_of_the_proxy_block():
    host = read("Caddyfile.snippet").split("\nvalio", 1)[1].split(" {", 1)[0]
    assert f"agent_mcp/server.py --http valio{host}\n" in read("junction-mcp.service")
