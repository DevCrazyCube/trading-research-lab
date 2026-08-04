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
import urllib.error
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


def endpoint_identity(endpoint):
    """The ONLY representation of an endpoint that may be persisted: scheme, host, explicit port.

    One contract, in the one module every transport already loads, because the leak this replaces was
    two sanitizers disagreeing. b9d's kept `parsed.path`; b11c's did not. That was harmless while the
    provider carried its key in the QUERY STRING and became a credential written into a collected
    artifact the moment the provider carried it in the PATH instead.

    So the rule is positive rather than a list of things to strip: build the identity from the two
    components that are safe by construction, and let everything else -- path, query, fragment and
    userinfo -- be absent because it was never copied, not because a filter caught it.

    * userinfo (`https://user:pass@host`) never appears: `hostname` excludes it by definition.
    * an IPv6 host is re-bracketed, because `hostname` strips the brackets and `https://::1` is not
      a parseable URL.
    * an explicit port is kept, because two endpoints on one host are two endpoints; a default port
      is not restated.
    * anything that is not an http(s) URL with a host is refused rather than guessed at.
    """
    parsed = urllib.parse.urlsplit(str(endpoint))
    if parsed.scheme not in ("http", "https"):
        raise TransportIdentityError(
            f"an endpoint identity needs an http or https scheme, got {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise TransportIdentityError("an endpoint identity needs a host")
    try:
        port = parsed.port
    except ValueError as error:
        raise TransportIdentityError(f"the endpoint port is not a number: {error}") from error
    if ":" in host:                      # IPv6 literal; hostname() has already dropped the brackets
        host = f"[{host}]"
    return f"{parsed.scheme}://{host}{f':{port}' if port else ''}"


def assert_endpoint_identity_is_safe(endpoint):
    """Belt for the braces: the identity must not contain any component that could carry a secret.

    Derived from the SOURCE url rather than from a token list, so it needs no knowledge of which
    provider hides its key where. If a path, query, fragment or userinfo string survived into the
    identity, that is the bug this exists to catch.
    """
    identity = endpoint_identity(endpoint)
    parsed = urllib.parse.urlsplit(identity)
    # STRUCTURAL, not a substring hunt. Searching the identity for each source component's text
    # false-positives the moment a component is short: a one-character password matches the letter
    # inside the hostname. Parsing the identity back and requiring the risky components to be ABSENT
    # is exact, and it cannot be fooled by a coincidence either way.
    present = [name for name, value in (("path", parsed.path), ("query", parsed.query),
                                        ("fragment", parsed.fragment),
                                        ("username", parsed.username),
                                        ("password", parsed.password)) if value]
    if present:
        raise TransportIdentityError(
            f"the endpoint identity {identity!r} still carries {present}; a persisted endpoint must "
            f"be scheme, host and explicit port only")
    source = urllib.parse.urlsplit(str(endpoint))
    if parsed.hostname != source.hostname or parsed.port != source.port:
        raise TransportIdentityError(
            f"the endpoint identity names a different host or port than the endpoint it came from")
    return identity


def is_client_refusal(status):
    """A 403 is the WAF refusing this client. Terminal everywhere, never retried."""
    return status == 403


# The one retry classification for every transport in the B11 stage pipeline. Stated once so the
# five call sites cannot drift: b9d already used exactly this set, and b7d and b9c retried only 429,
# which made a single transient gateway error during enumeration or signature inventory fatal to a
# run measured in tens of hours.
#
# 408 and 5xx are the server saying "not now". 403 is the server saying "not you" -- Cloudflare's
# `error code: 1010` for the client identity, and Chainstack's `-32002` for a plan entitlement. No
# number of retries changes an answer about who you are, and retrying one spends the budget and then
# reports a transport failure, which reads as an unlucky network.
RETRYABLE_STATUSES = (408, 429, 500, 502, 503, 504)


def is_retryable_status(status):
    """Whether an HTTP status is worth another attempt. A 403 never is."""
    if is_client_refusal(status):
        return False
    return status in RETRYABLE_STATUSES


def is_retryable_error(error):
    """Classify a transport exception. A non-HTTP transport fault is retryable; a 403 is not.

    `urllib.error.HTTPError` is a subclass of `URLError`, so it must be tested FIRST -- an isinstance
    chain in the other order would classify every 403 as a retryable connection problem.
    """
    if isinstance(error, urllib.error.HTTPError):
        return is_retryable_status(error.code)
    return isinstance(error, (urllib.error.URLError, TimeoutError, OSError))


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
