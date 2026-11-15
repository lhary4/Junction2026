"""deploy/: the hosted demo. The page, the proxy block and the unit files must agree on names and ports."""

import re
from fnmatch import fnmatchcase
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
    mcp_block = proxy[proxy.index("handle @mcp") : proxy.index("handle /mcp*")]
    assert "flush_interval -1" in mcp_block  # streamed answers are not buffered
    assert "header_up -Origin" in mcp_block  # the MCP server answers 403 to any Origin header it was not given


def is_closed(path: str) -> bool:
    """Whether the proxy answers 404 to this address: it matches a pattern of the `@closed path` line."""
    line = re.search(r"^\s*@closed path (.+)$", read("Caddyfile.snippet"), re.MULTILINE)
    assert line, "no @closed line in the proxy"
    return any(fnmatchcase(path, pattern) for pattern in line.group(1).split())


def test_the_proxy_closes_what_no_page_calls_before_it_passes_anything_on():
    proxy = read("Caddyfile.snippet")
    assert re.search(r"handle @closed \{\s*respond 404\s*\}", proxy)
    for name in PAGE_SERVICES:  # `route` is read top to bottom: the 404 comes before the block that passes on
        assert proxy.index("handle @closed") < proxy.index(f"handle /{name}/*")
    # The agent's own routes, read from the driver itself: a new one is closed without touching this test.
    driver = (ROOT / "scenarios" / "run.py").read_text(encoding="utf-8")
    agent_routes = re.findall(r'@api\.\w+\("(/agent/[^"]*)"\)', driver)
    assert agent_routes, "the driver has no /agent/ route any more"
    for route in agent_routes:
        assert is_closed(f"/driver{route}")
    assert is_closed("/harness/authorize")  # only the driver calls it, on the server itself
    for prefix in ("", "/driver", "/harness"):
        for page in ("/docs", "/redoc", "/openapi.json"):
            assert is_closed(prefix + page)


def test_the_proxy_leaves_open_every_address_the_page_calls():
    script = (ROOT / "surface" / "static" / "portal.js").read_text(encoding="utf-8")
    # Every `${DRIVER_URL}/...` the page writes, as the address the proxy sees. A `${...}` part becomes the word x.
    paths = []
    for name, path in re.findall(r"\$\{(DRIVER|HARNESS|ASSISTANT)_URL\}(/[^`\"]*)", script):
        paths.append(f"/{name.lower()}" + re.sub(r"\$\{[^}]*\}", "x", path))
    assert "/driver/state" in paths and "/harness/policy" in paths, "the page's calls were not found"
    for path in paths:
        assert not is_closed(path), f"the page calls {path} and the proxy closes it"


def test_every_port_the_proxy_calls_has_its_relay():
    wanted = read("junction-demo.service")
    for port in set(re.findall(r"reverse_proxy 172\.18\.0\.1:(\d+)", read("Caddyfile.snippet"))):
        assert f"junction-bridge@{port}.socket" in wanted


def test_the_mcp_unit_answers_to_the_host_of_the_proxy_block():
    host = read("Caddyfile.snippet").split("\nvalio", 1)[1].split(" {", 1)[0]
    assert f"agent_mcp/server.py --http valio{host}\n" in read("junction-mcp.service")
