"""Every HTTP transport reachable from B11c's nine frozen stage commands sends one fixed identity.

The tests that matter here are the ones that fail when somebody adds a sixth transport and forgets:
`test_the_audit_catches_a_call_site_that_bypasses_the_helper` proves the audit can see such a site,
and `test_no_stage_reachable_module_builds_its_own_request` runs it over the real modules.

A Cloudflare block is the reason this exists, so each transport is driven with a synthetic
`HTTP 403 / error code: 1010` and required to give up after exactly one attempt. A permanent refusal
that gets retried eight times reports itself as a flaky network instead of as a rejected client.
"""
import contextlib
import importlib.util
import io
import json
import pathlib
import sys
import unittest
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(name, filename):
    """Loaded privately, NOT registered in `sys.modules`.

    Registering would replace whatever instance another test file already holds under that name, and
    a later test asserting two references are the same module object would then fail for a reason
    that has nothing to do with what it is testing. That is a real failure this file caused once.
    """
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HTTP = load("rpc_http_identity", "rpc_http_identity.py")
B11A = load("b11a_window_freeze", "b11a_window_freeze.py")
B7D = load("b7d_create_enumerator", "b7d_create_enumerator.py")
B9C = load("b9c_signature_inventory", "b9c_signature_inventory.py")
B9D = load("b9d_transaction_bodies", "b9d_transaction_bodies.py")

# The modules the nine frozen stage commands execute, plus the watcher's own transport module.
STAGE_REACHABLE = (
    "b11a_window_freeze.py",        # the watcher's getSlot preflight
    "b11c_maturity_watcher.py",     # the supervisor itself
    "b7d_create_enumerator.py",     # enumerate_creates
    "b9c_signature_inventory.py",   # signature_inventory
    "b9d_transaction_bodies.py",    # program_boundary, transaction_bodies, decode_and_reserves
    "b11d_cohort_adapter.py",       # build_cohort (offline)
    "b9e_reserve_coverage.py",      # reserve_coverage_gate (offline)
    "b9f_failure_coverage.py",      # failure_coverage_gate (offline)
    "b10a_simulator_kernel.py",     # simulator_replay_gate (offline)
)

URL = "https://example.invalid/rpc"


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exception):
        return False


@contextlib.contextmanager
def captured(payload=None, raise_error=None):
    """Replace the real opener, record every Request, and answer with canned bytes."""
    requests = []
    body = json.dumps({"jsonrpc": "2.0", "id": 1,
                       "result": payload if payload is not None else 1}).encode()

    def opener(request, timeout=None):
        requests.append(request)
        if raise_error is not None:
            raise raise_error
        return Response(body)

    original = urllib.request.urlopen
    urllib.request.urlopen = opener
    try:
        yield requests
    finally:
        urllib.request.urlopen = original


def cloudflare_403():
    return urllib.error.HTTPError(URL, 403, "Forbidden", {},
                                  io.BytesIO(b"error code: 1010"))


class TestTheIdentityItself(unittest.TestCase):
    def test_the_user_agent_is_exactly_the_pinned_value(self):
        """Exact, so a reformat or a well-meaning tweak shows up as a failing test."""
        self.assertEqual(HTTP.USER_AGENT, "solana-rpc-client/1.0")

    def test_the_headers_are_exactly_content_type_and_user_agent(self):
        self.assertEqual(HTTP.headers(),
                         {"Content-Type": "application/json",
                          "User-Agent": "solana-rpc-client/1.0"})

    def test_the_identity_is_stable_across_calls_and_between_modules(self):
        self.assertEqual(HTTP.headers(), HTTP.headers())
        for module in (B11A, B7D, B9C, B9D):
            with self.subTest(module=module.__name__):
                self.assertEqual(module.HTTP.USER_AGENT, HTTP.USER_AGENT)

    def test_a_caller_cannot_mutate_the_shared_headers(self):
        first = HTTP.headers()
        first["User-Agent"] = "tampered"
        self.assertEqual(HTTP.headers()["User-Agent"], HTTP.USER_AGENT)

    def test_the_identity_carries_no_credential_or_endpoint_material(self):
        self.assertTrue(HTTP.assert_identity_safe())
        for bad in ("client?api-key=k", "https://host/path", "x=1", "bearer abc",
                    "secret-client", "token/1.0"):
            with self.subTest(bad=bad):
                with self.assertRaises(HTTP.TransportIdentityError):
                    HTTP.assert_identity_safe(bad)

    def test_whitespace_is_refused_so_a_hostname_cannot_creep_in(self):
        with self.assertRaises(HTTP.TransportIdentityError):
            HTTP.assert_identity_safe("client 1.0")

    def test_an_empty_or_non_string_identity_is_refused(self):
        for bad in ("", None, 7):
            with self.subTest(bad=bad):
                with self.assertRaises(HTTP.TransportIdentityError):
                    HTTP.assert_identity_safe(bad)

    def test_there_is_no_per_provider_branching_in_the_helper(self):
        """One header for every endpoint. A host named in here would be a rule nobody can test."""
        source = (ROOT / "scripts" / "rpc_http_identity.py").read_text()
        for host in ("helius", "chainstack", "mainnet-beta", "quicknode", "alchemy", "triton"):
            with self.subTest(host=host):
                self.assertNotIn(f'"{host}', source)
                self.assertNotIn(f"'{host}", source)

    def test_the_body_must_already_be_bytes(self):
        """Encoding here would change the bytes the caller meant to send."""
        with self.assertRaises(HTTP.TransportIdentityError):
            HTTP.json_rpc_request(URL, '{"jsonrpc":"2.0"}')

    def test_the_body_is_passed_through_byte_for_byte(self):
        body = b'{"jsonrpc":"2.0","id":1,"method":"getSlot","params":[]}'
        self.assertEqual(HTTP.json_rpc_request(URL, body).data, body)


class TestEveryTransportSendsIt(unittest.TestCase):
    def assert_carries_identity(self, request):
        # urllib title-cases header keys it stores, so ask the way urllib answers.
        self.assertEqual(request.get_header("User-agent"), HTTP.USER_AGENT)
        self.assertEqual(request.get_header("Content-type"), "application/json")

    def test_b11a_preflight_getslot(self):
        with captured(payload=123) as requests:
            value = B11A.preflight_call(URL, "getSlot", [{"commitment": "finalized"}])
        self.assertEqual(value, 123)
        self.assertEqual(len(requests), 1)
        self.assert_carries_identity(requests[0])

    def test_b7d_getblock(self):
        with captured(payload={"transactions": []}) as requests:
            B7D.rpc_block(URL, 700, retries=1)
        self.assertEqual(len(requests), 1)
        self.assert_carries_identity(requests[0])

    def test_b7d_getblocks(self):
        with captured(payload=[700, 701]) as requests:
            produced, error = B7D.rpc_produced_slots(URL, 700, 701, retries=1)
        self.assertIsNone(error)
        self.assertEqual(produced, {700, 701})
        self.assertEqual(len(requests), 1)
        self.assert_carries_identity(requests[0])

    def test_b9c_request_bytes(self):
        with captured(payload=[]) as requests:
            raw, result = B9C.request_bytes(URL, "getSignaturesForAddress", ["x"], retries=1)
        self.assertEqual(result, [])
        self.assertEqual(len(requests), 1)
        self.assert_carries_identity(requests[0])

    def test_b9d_rpc_request(self):
        captured_requests = []
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"slot": 7}}).encode()

        def opener(request, timeout=None):
            captured_requests.append(request)
            return Response(body)

        raw, result = B9D.rpc_request(URL, "getTransaction", ["sig"], opener=opener)
        self.assertEqual(result, {"slot": 7})
        self.assertEqual(len(captured_requests), 1)
        self.assert_carries_identity(captured_requests[0])

    def test_all_five_transports_send_the_same_bytes_for_the_header(self):
        seen = set()
        with captured(payload=1) as requests:
            B11A.preflight_call(URL, "getSlot", [{"commitment": "finalized"}])
            B7D.rpc_produced_slots(URL, 700, 701, retries=1)
            B9C.request_bytes(URL, "getSignaturesForAddress", ["x"], retries=1)
        for request in requests:
            seen.add(request.get_header("User-agent"))
        with captured(payload={"transactions": []}) as more:
            B7D.rpc_block(URL, 700, retries=1)
        seen.add(more[0].get_header("User-agent"))
        self.assertEqual(seen, {HTTP.USER_AGENT})


class TestRawSemanticsPreserved(unittest.TestCase):
    """Headers are transport metadata. Nothing the pipeline stores may change because of them."""

    def test_b9d_sends_the_same_canonical_body_as_before(self):
        expected = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTransaction",
                               "params": ["sig"]}, separators=(",", ":")).encode()
        captured_requests = []

        def opener(request, timeout=None):
            captured_requests.append(request)
            return Response(json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}).encode())

        B9D.rpc_request(URL, "getTransaction", ["sig"], opener=opener)
        self.assertEqual(captured_requests[0].data, expected)

    def test_b9c_sends_the_same_canonical_body_as_before(self):
        expected = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
                               "params": ["x"]}, separators=(",", ":")).encode()
        with captured(payload=[]) as requests:
            B9C.request_bytes(URL, "getSignaturesForAddress", ["x"], retries=1)
        self.assertEqual(requests[0].data, expected)

    def test_b9cs_request_key_is_over_method_and_params_only(self):
        """The preserved-response key must not move, or every stored response is orphaned.

        Pinned to the digest of `["getSignaturesForAddress", ["x"]]` so that a key which started
        folding in a header, an endpoint or anything else fails here rather than quietly stranding
        every raw response already on disk.
        """
        import hashlib
        expected = hashlib.sha256(json.dumps(
            ["getSignaturesForAddress", ["x"]], sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(B9C.request_key("getSignaturesForAddress", ["x"]), expected)

    def test_the_request_method_is_still_post(self):
        request = HTTP.json_rpc_request(URL, b"{}")
        self.assertEqual(request.get_method(), "POST")

    def test_the_url_is_untouched(self):
        request = HTTP.json_rpc_request(URL, b"{}")
        self.assertEqual(request.full_url, URL)


class TestCloudflare403IsTerminal(unittest.TestCase):
    """`error code: 1010` is the WAF refusing this client. Every retry gets the same answer."""

    def test_b11a_preflight_does_not_retry(self):
        with captured(raise_error=cloudflare_403()) as requests:
            with self.assertRaises(urllib.error.HTTPError):
                B11A.preflight_call(URL, "getSlot", [{"commitment": "finalized"}])
        self.assertEqual(len(requests), 1)

    def test_b7d_getblock_does_not_retry(self):
        with captured(raise_error=cloudflare_403()) as requests:
            slot, status, _result, error = B7D.rpc_block(URL, 700, retries=8)
        self.assertEqual(status, "error")
        self.assertIn("403", error)
        self.assertEqual(len(requests), 1, "a permanent client refusal must not be retried")

    def test_b7d_getblocks_does_not_retry(self):
        with captured(raise_error=cloudflare_403()) as requests:
            produced, error = B7D.rpc_produced_slots(URL, 700, 701, retries=8)
        self.assertIsNone(produced)
        self.assertIn("403", error)
        self.assertEqual(len(requests), 1, "a permanent client refusal must not be retried")

    def test_b9c_does_not_retry(self):
        with captured(raise_error=cloudflare_403()) as requests:
            with self.assertRaises(urllib.error.HTTPError):
                B9C.request_bytes(URL, "getSignaturesForAddress", ["x"], retries=8)
        self.assertEqual(len(requests), 1)

    def test_b9d_does_not_retry(self):
        attempts = []

        def opener(request, timeout=None):
            attempts.append(request)
            raise cloudflare_403()

        with self.assertRaises(B9D.FreezeViolation):
            B9D.rpc_request(URL, "getTransaction", ["sig"], opener=opener, retries=8)
        self.assertEqual(len(attempts), 1)

    def test_a_429_is_still_retried_so_the_403_rule_is_not_a_blanket_one(self):
        """The point is that 403 is terminal, not that every HTTP error is."""
        attempts = []

        def opener(request, timeout=None):
            attempts.append(request)
            raise urllib.error.HTTPError(URL, 429, "Too Many Requests",
                                         {"Retry-After": "0"}, io.BytesIO(b""))

        with self.assertRaises(B9D.FreezeViolation):
            B9D.rpc_request(URL, "getTransaction", ["sig"], opener=opener, retries=2)
        self.assertEqual(len(attempts), 3)

    def test_the_client_refusal_predicate_names_only_403(self):
        self.assertTrue(HTTP.is_client_refusal(403))
        for status in (200, 400, 401, 404, 408, 429, 500, 502, 503, 504):
            with self.subTest(status=status):
                self.assertFalse(HTTP.is_client_refusal(status))


class TestTheAuditCatchesAMissingCallSite(unittest.TestCase):
    def test_no_stage_reachable_module_builds_its_own_request(self):
        paths = [ROOT / "scripts" / name for name in STAGE_REACHABLE]
        self.assertTrue(HTTP.assert_no_unrouted_request_sites(paths))

    def test_the_audit_catches_a_call_site_that_bypasses_the_helper(self):
        """The regression this whole patch is one edit away from: a new transport, no header."""
        import tempfile
        directory = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
        offender = directory / "b99_new_transport.py"
        offender.write_text(
            "import urllib.request\n"
            "def fetch(url, body):\n"
            "    request = urllib.request.Request(url, data=body,\n"
            "                                     headers={'Content-Type': 'application/json'})\n"
            "    return urllib.request.urlopen(request)\n")
        with self.assertRaises(HTTP.TransportIdentityError) as caught:
            HTTP.assert_no_unrouted_request_sites([offender])
        self.assertIn("b99_new_transport.py", str(caught.exception))
        self.assertIn("3", str(caught.exception))          # the offending line number

    def test_the_audit_catches_a_bare_Request_call_too(self):
        import tempfile
        directory = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
        offender = directory / "b98_bare.py"
        offender.write_text("from urllib.request import Request\n"
                            "def go(url):\n    return Request(url)\n")
        with self.assertRaises(HTTP.TransportIdentityError):
            HTTP.assert_no_unrouted_request_sites([offender])

    def test_a_request_named_in_a_comment_or_docstring_is_not_a_call_site(self):
        """Prose describing the rule must not trip the rule. The AST, not the text."""
        import tempfile
        directory = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
        clean = directory / "b97_prose.py"
        clean.write_text('"""Never call urllib.request.Request(url) directly."""\n'
                         "# urllib.request.Request(url) is forbidden here\n"
                         "VALUE = 1\n")
        self.assertTrue(HTTP.assert_no_unrouted_request_sites([clean]))

    def test_the_helper_itself_is_exempt_because_it_is_the_routed_site(self):
        self.assertTrue(HTTP.assert_no_unrouted_request_sites(
            [ROOT / "scripts" / "rpc_http_identity.py"]))


class TestNoSecretReachesTheHeaderOrALog(unittest.TestCase):
    def test_the_helper_reads_no_environment_variable(self):
        source = (ROOT / "scripts" / "rpc_http_identity.py").read_text()
        for forbidden in ("os.environ", "getenv", "SOLANA_RPC_URL", "sys.argv"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_the_header_does_not_vary_with_the_url(self):
        first = HTTP.json_rpc_request("https://a.invalid/rpc?api-key=SECRET", b"{}")
        second = HTTP.json_rpc_request("https://b.invalid/rpc", b"{}")
        self.assertEqual(first.get_header("User-agent"), second.get_header("User-agent"))
        self.assertNotIn("SECRET", first.get_header("User-agent"))

    def test_no_header_value_contains_the_urls_query_string(self):
        request = HTTP.json_rpc_request("https://host.invalid/rpc?api-key=abc123", b"{}")
        for value in request.headers.values():
            with self.subTest(value=value):
                self.assertNotIn("abc123", value)
                self.assertNotIn("api-key", value.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
