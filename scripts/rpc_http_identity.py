"""One fixed request identity for every JSON-RPC call the B11 pipeline makes.

Python's urllib announces itself as `Python-urllib/3.x`. Providers behind a WAF refuse that outright:
Chainstack answers `HTTP 403` with the body `error code: 1010`, which is Cloudflare refusing the
CLIENT. That is a permanent refusal, not a transport fault, and no retry can turn it into a success —
which is why every transport here treats a 403 as terminal rather than backing off against it.

The header is:

* **fixed** — one pinned literal. A value that varied per run, per host or per process would make two
  runs' requests differ in a way no artifact records, and a preserved raw response would no longer
  describe the request that produced it.
* **non-identifying** — a user agent is handed to a third party on every call. This one carries no
  operator name, no host name, no path, no run identifier and no credential.
* **unconditional** — there is no per-provider branching anywhere in this module. Sending one honest
  identity to every endpoint is the whole design; a header that appeared only for the host that
  demanded it would be a rule nobody could test on any other host.

Every request the nine frozen stage commands make is built here, so a new call site that bypasses
this module is a defect rather than a variation, and `assert_no_unrouted_request_sites` finds it.
"""
import ast
import pathlib
import urllib.request

SCRIPTS = pathlib.Path(__file__).resolve().parent

# Pinned. Tests assert this exact value, so a change is a deliberate edit with a visible diff and
# never an accident of formatting.
USER_AGENT = "solana-rpc-client/1.0"

CONTENT_TYPE = "application/json"

# Anything that would mean a credential, a query string or an endpoint had reached the header.
CREDENTIAL_MARKERS = ("?", "=", "://", "api-key", "api_key", "apikey", "authorization", "bearer",
                      "secret", "token")


class TransportIdentityError(RuntimeError):
    """The identity is wrong, or a request was built without it."""


def assert_identity_safe(user_agent=USER_AGENT):
    """The header must be a plain fixed token and must not carry anything private.

    Checked at build time rather than trusted, because the failure mode is silent: a user agent
    assembled from a URL would ship a credential to a third party on every request and nothing in
    the response would show it happened.
    """
    if not isinstance(user_agent, str) or not user_agent:
        raise TransportIdentityError("the user agent must be a non-empty string")
    lowered = user_agent.lower()
    found = sorted({marker for marker in CREDENTIAL_MARKERS if marker in lowered})
    if found:
        raise TransportIdentityError(
            f"the user agent {user_agent!r} contains {found}; a user agent is sent to a third "
            f"party and must carry no endpoint, query string or credential material")
    if any(character.isspace() for character in user_agent):
        raise TransportIdentityError(
            f"the user agent {user_agent!r} contains whitespace; the pinned identity is a single "
            f"token so that it cannot pick up a hostname or a path by accident")
    return True


def headers():
    """A fresh copy, so a caller that mutates its headers cannot alter anyone else's."""
    assert_identity_safe()
    return {"Content-Type": CONTENT_TYPE, "User-Agent": USER_AGENT}


def json_rpc_request(url, body, method="POST"):
    """The one place a JSON-RPC `Request` is constructed.

    The body is passed through byte for byte. Headers are transport metadata and are not part of any
    preserved request record or response digest, so routing every call through here changes what the
    server sees about the client and nothing about what the pipeline stores.
    """
    if not isinstance(body, (bytes, bytearray)):
        raise TransportIdentityError(
            f"the request body must be bytes, got {type(body).__name__}; encoding it here would "
            f"change the bytes the caller intended to send")
    return urllib.request.Request(url, data=bytes(body), headers=headers(), method=method)


def is_client_refusal(status):
    """A 403 is the WAF refusing this client. Terminal everywhere, never retried."""
    return status == 403


# ----------------------------------------------------------------------------------------------
# The audit that keeps this the only door
# ----------------------------------------------------------------------------------------------

def request_construction_sites(path):
    """Every `urllib.request.Request(...)` built in a module, by line, read from the AST.

    The AST rather than the text, so a mention in a comment or a docstring is documentation and a
    call is a call.
    """
    tree = ast.parse(pathlib.Path(path).read_text())
    sites = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        name = None
        if isinstance(target, ast.Attribute):
            name = target.attr
        elif isinstance(target, ast.Name):
            name = target.id
        if name != "Request":
            continue
        # `urllib.request.Request` and a bare `Request` both count; this module's own call is the
        # routed one and is excluded by the caller, not silently here.
        sites.append(node.lineno)
    return sites


def assert_no_unrouted_request_sites(paths):
    """Refuse if any module builds a JSON-RPC request without coming through `json_rpc_request`.

    This is the check that catches a call site added later and forgotten. It cannot be satisfied by
    adding a header by hand at a new site — the point is that there is one identity, in one place, so
    a reader never has to check five transports to learn what this client says it is.
    """
    unrouted = {}
    for path in paths:
        path = pathlib.Path(path)
        if path.resolve() == pathlib.Path(__file__).resolve():
            continue
        sites = request_construction_sites(path)
        if sites:
            unrouted[path.name] = sites
    if unrouted:
        raise TransportIdentityError(
            f"these modules build a urllib Request directly instead of through "
            f"{pathlib.Path(__file__).name}: {unrouted}. Every JSON-RPC request must carry the one "
            f"pinned identity, and a site that builds its own would silently send urllib's default")
    return True
