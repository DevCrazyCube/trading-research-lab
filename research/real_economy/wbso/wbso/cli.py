"""Command line: probe, scan, brief, dryrun, lint.

    python -m wbso.cli probe                    # re-verify every source is up, free and open
    python -m wbso.cli scan --max-orgs 60       # run the funnel, write data/candidates.jsonl
    python -m wbso.cli brief --limit 10         # generate briefings + dossiers from that file
    python -m wbso.cli dryrun --limit 10        # scan + brief + DRYRUN_REPORT.md, in one go
    python -m wbso.cli lint                     # re-lint everything already generated

None of these send anything. There is no `send` subcommand and there is not going to be one in this
package: sending is an owner action (README §2), and the absence of the verb is the safeguard.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

from . import briefing as briefing_mod
from . import scanner as scanner_mod
from .http_client import PoliteClient
from .params import load_params
from .scanner import ScanConfig
from .sources import peppol, tenderned

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BRIEFINGS = ROOT / "briefings"
LOGS = ROOT / "logs"
CANDIDATES = DATA / "candidates.jsonl"


def _client(args, *, budget: int) -> PoliteClient:
    return PoliteClient(
        cache_dir=DATA / "cache",
        budget=budget,
        receipts_path=LOGS / "requests.jsonl",
        offline=getattr(args, "offline", False),
    )


def _today(args) -> str:
    return getattr(args, "today", None) or dt.date.today().isoformat()


# --- probe ---------------------------------------------------------------------------------


def cmd_probe(args) -> int:
    client = _client(args, budget=12)
    out: dict = {"probed_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "sources": {}}

    status, payload = client.get("https://api.github.com/rate_limit", note="probe rate_limit")
    out["sources"]["github_rate_limit"] = {
        "status": status,
        "search": (payload or {}).get("resources", {}).get("search"),
        "core": (payload or {}).get("resources", {}).get("core"),
    }
    status, payload = client.get(
        "https://api.github.com/search/users?q=type:org+location:Netherlands&per_page=1",
        note="probe org population",
    )
    out["sources"]["github_nl_orgs"] = {
        "status": status,
        "total_count": (payload or {}).get("total_count"),
        "note": "search returns at most 1,000 of these; partition by created: windows",
    }
    out["sources"]["peppol"] = peppol.probe(client)

    pubs = tenderned.fetch_publications(client, pages=1, size=100)
    out["sources"]["tenderned_demand"] = tenderned.ict_demand_signal(pubs)
    if pubs:
        out["sources"]["tenderned_supplier_field"] = tenderned.supplier_field_probe(
            client, pubs[0].get("publicatieId")
        )

    out["client"] = client.summary()
    path = LOGS / "probe_report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False)[:4000])
    print(f"\nwritten: {path}")
    return 0


# --- scan ----------------------------------------------------------------------------------


def cmd_scan(args) -> int:
    cfg = ScanConfig(
        created_from=args.created_from,
        created_to=args.created_to,
        window_months=args.window_months,
        pushed_since=args.pushed_since,
        max_orgs_screened=args.max_orgs,
        max_enriched=args.max_enriched,
        fetch_sites=args.fetch_sites,
        site_budget=args.site_budget,
        use_peppol=not args.no_peppol,
    )
    client = _client(args, budget=args.budget)
    candidates, funnel = scanner_mod.scan(
        client, cfg, today_iso=_today(args), progress=(lambda m: print(m, file=sys.stderr))
    )
    n = scanner_mod.write_candidates(CANDIDATES, candidates)
    report = scanner_mod.scan_report(candidates, funnel)
    report["client"] = client.summary()
    (LOGS / "scan_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\n{n} candidates -> {CANDIDATES}", file=sys.stderr)
    return 0


# --- rescore -------------------------------------------------------------------------------


def cmd_rescore(args) -> int:
    """Re-apply exclusion and scoring rules to an existing scan. No network, no refetch.

    Rules change when a live run shows what they missed; re-running the scan to test a rule change
    would cost ten minutes of rate-limited requests and, worse, would change the data underneath the
    comparison. This keeps the fetched evidence fixed and moves only the rules.
    """
    cfg = ScanConfig(pushed_since=args.pushed_since)
    candidates = scanner_mod.read_candidates(args.candidates or CANDIDATES)
    before = sum(1 for c in candidates if not c.excluded)
    for cand in candidates:
        scanner_mod.apply_exclusions(cand, cfg)
        scanner_mod.score_candidate(cand, today_iso=_today(args))
    candidates.sort(key=lambda c: (-c.score, c.github_login))
    scanner_mod.write_candidates(args.candidates or CANDIDATES, candidates)

    old = json.loads((LOGS / "scan_report.json").read_text(encoding="utf-8"))
    report = scanner_mod.scan_report(candidates, old["funnel"])
    report["client"] = old.get("client", {})
    report["rescored"] = {"kept_before": before, "kept_after": report["kept"]}
    (LOGS / "scan_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({k: report[k] for k in ("scanned", "kept", "excluded", "keep_rate",
                                             "keep_rate_of_enriched", "rescored")}, indent=2))
    return 0


# --- brief ---------------------------------------------------------------------------------


def cmd_brief(args) -> int:
    params = load_params(args.params)
    sender = briefing_mod.load_sender(args.sender)
    candidates = scanner_mod.read_candidates(args.candidates or CANDIDATES)
    keep = [c for c in candidates if not c.excluded and (c.website or c.public_email)]
    keep.sort(key=lambda c: -c.score)
    chosen = keep[: args.limit]
    if not chosen:
        print("no candidates survived exclusion with a public contact channel", file=sys.stderr)
        return 2

    BRIEFINGS.mkdir(parents=True, exist_ok=True)
    results = []
    today = _today(args)
    for i, cand in enumerate(chosen, 1):
        text, dossier, lint = briefing_mod.generate(cand, params, sender, today_iso=today)
        stem = f"{i:02d}_{cand.github_login.lower()}"
        (BRIEFINGS / f"{stem}.md").write_text(text, encoding="utf-8")
        (BRIEFINGS / f"{stem}.dossier.json").write_text(
            json.dumps(dossier, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        results.append(
            {
                "file": f"{stem}.md",
                "candidate": cand.candidate_id,
                "name": cand.display_name,
                "website": cand.website,
                "score": cand.score,
                "review_flags": cand.signals.get("review_flags", []),
                "lint_ok": lint.ok,
                "lint": lint.summary(),
            }
        )
        print(f"{stem}.md  score={cand.score}  lint={lint.summary()}", file=sys.stderr)

    failed = [r for r in results if not r["lint_ok"]]
    (LOGS / "briefing_report.json").write_text(
        json.dumps(
            {
                "generated": today,
                "count": len(results),
                "lint_failures": len(failed),
                "sender_ready_to_send": sender["_ready_to_send"],
                "sender_placeholders": sender["_placeholders"],
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"generated": len(results), "lint_failures": len(failed)}, indent=2))
    return 1 if failed else 0


# --- lint ----------------------------------------------------------------------------------


def cmd_lint(args) -> int:
    from .ethics import lint_briefing

    bad = 0
    for path in sorted(BRIEFINGS.glob("*.md")):
        dossier_path = path.with_suffix("").with_suffix(".dossier.json")
        urls: list[str] = []
        if dossier_path.exists():
            doc = json.loads(dossier_path.read_text(encoding="utf-8"))
            urls = list(doc.get("lint_allowed_urls") or [])
            if not urls:
                urls = [e["url"] for e in doc.get("evidence", []) if e.get("url")]
        result = lint_briefing(path.read_text(encoding="utf-8"), evidence_urls=urls)
        status = "OK " if result.ok else "FAIL"
        print(f"{status} {path.name}: {result.summary()}")
        bad += 0 if result.ok else 1
    print(f"\n{bad} failing briefing(s)")
    return 1 if bad else 0


# --- dryrun --------------------------------------------------------------------------------


def cmd_dryrun(args) -> int:
    rc = cmd_scan(args)
    if rc:
        return rc
    args.candidates = CANDIDATES
    rc = cmd_brief(args)
    write_dryrun_report(args)
    return rc


def write_dryrun_report(args) -> pathlib.Path:
    scan = json.loads((LOGS / "scan_report.json").read_text(encoding="utf-8"))
    brief = json.loads((LOGS / "briefing_report.json").read_text(encoding="utf-8"))
    params = load_params(args.params)
    funnel = scan["funnel"]
    lines: list[str] = []
    a = lines.append

    a("# WBSO scanner — dry run\n")
    a(
        "Generated by `python -m wbso.cli dryrun`. **Nothing was sent, no account was created, "
        "no money was spent.** Every briefing in `briefings/` is stamped CONCEPT and the sender "
        "profile still carries placeholders, so none of them is addressable.\n"
    )
    a(f"- run date: **{brief['generated']}**")
    a(f"- RVO parameters frozen on: **{params.frozen_on.isoformat()}**")
    a(f"- briefings generated: **{brief['count']}**, lint failures: **{brief['lint_failures']}**")
    a(f"- sender profile ready to send: **{brief['sender_ready_to_send']}** "
      f"({len(brief['sender_placeholders'])} placeholders outstanding)\n")

    a("## The funnel, with its losses\n")
    a("| stage | count |")
    a("|---|--:|")
    a(f"| org stubs enumerated (GitHub `location:Netherlands`) | {funnel['orgs_enumerated']} |")
    a(f"| screened (one repo search each) | {funnel['orgs_screened']} |")
    a(f"| passed screen (own non-fork repo pushed since {funnel['config']['pushed_since']}) | {funnel['passed_screen']} |")
    a(f"| enriched (org profile + Peppol) | {funnel['enriched']} |")
    a(f"| kept after exclusions | {scan['kept']} |")
    a(f"| kept **with** a public contact channel | {scan['kept_with_contact']} |")
    a(f"| kept with an NL legal-entity corroboration (Peppol) | {scan['kept_with_peppol']} |\n")
    if funnel.get("stopped_early"):
        a(f"Run stopped early: `{funnel['stopped_early']}`\n")
    a(f"Keep rate over everything scanned: **{scan['keep_rate']}**; over the candidates whose "
      f"profile was actually fetched: **{scan.get('keep_rate_of_enriched')}**. "
      "T26 §8 said the population proxy is what decides whether this pipeline is worth anything. "
      "These two numbers are the scanner's answer — and note they measure the *rules*, not the "
      "truth: a kept candidate is one no rule could reject, not one that qualifies for the WBSO.\n")

    a("## Why candidates were dropped\n")
    a("| reason | n |")
    a("|---|--:|")
    for reason, n in scan["exclusion_reasons"]:
        a(f"| {reason} | {n} |")
    a("")

    a("## The briefings\n")
    a("| file | company | score | lint | doubts the rules could not settle |")
    a("|---|---|--:|---|---|")
    for r in brief["results"]:
        flags = "; ".join(r.get("review_flags") or []) or "—"
        a(f"| `{r['file']}` | {r['name']} | {r['score']} | {r['lint']} | {flags} |")
    a("")
    a(
        "The last column is the honest part. A rule can drop a university lab by its hostname and a "
        "scouting group by its name — both were found in the first live run and both are now "
        "excluded by rule — but no rule reliably distinguishes a two-person software company from a "
        "volunteer project that happens to look like one. That judgement is the owner's, which is "
        "what the dossier files are for.\n"
    )

    a("## Request budget\n")
    client = scan.get("client", {})
    receipts = LOGS / "requests.jsonl"
    total = sum(1 for _ in receipts.open(encoding="utf-8")) if receipts.exists() else None
    a(f"- live requests in the last run: **{client.get('requests_made')}** of a budget of "
      f"{client.get('budget')}")
    a(f"- served from the on-disk cache instead: {client.get('cache_hits')}")
    a(f"- cumulative requests across every run in `logs/requests.jsonl`: **{total}**")
    a(f"- by host, last run: `{client.get('by_host')}`")
    a(
        "\nThe low live-request count is the cache doing its job, not a small scan: the population "
        "was fetched over earlier runs and re-runs are nearly free. Unauthenticated GitHub allows "
        "~10 search requests a minute and 60 core requests an hour, which is the real constraint "
        "on how fast this can grow — roughly 500 organisations screened per hour, no token needed.\n"
    )

    a("## What this dry run does not show\n")
    a(
        "- **Whether any of these companies is actually eligible.** Nothing here can show that; "
        "RVO decides, on facts (technical novelty, hours, payroll) that are not public.\n"
        "- **Whether the briefing earns a reply.** That is the frozen test in README §3 and it "
        "requires the owner to send. Until 100 are sent, the reply rate is unmeasured, and the "
        "programme's own rule is that an unmeasured rate is not a rate.\n"
        "- **Precision of the population proxy.** The keep rate above is a scanner statistic, not "
        "a truth statistic: it says how many candidates survived our rules, not how many are real "
        "NL SMEs doing qualifying R&D. Only the owner reading the dossiers can say that, and "
        "README §6 asks for exactly that judgement on this sample.\n"
    )

    path = ROOT / "DRYRUN_REPORT.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"written: {path}", file=sys.stderr)
    return path


# --- argument parsing ----------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wbso", description=__doc__)
    p.add_argument("--offline", action="store_true", help="use only the on-disk cache")
    p.add_argument("--today", help="override today's date (ISO) for reproducible output")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("probe", help="re-verify every public source")
    sp.set_defaults(func=cmd_probe)

    ss = sub.add_parser("scan", help="run the candidate funnel")
    ss.add_argument("--created-from", default="2016-01-01")
    ss.add_argument("--created-to", default="2026-06-30")
    ss.add_argument("--window-months", type=int, default=12)
    ss.add_argument("--pushed-since", default="2026-02-01")
    ss.add_argument("--max-orgs", type=int, default=60)
    ss.add_argument("--max-enriched", type=int, default=25)
    ss.add_argument("--budget", type=int, default=150, help="hard cap on HTTP requests")
    ss.add_argument("--fetch-sites", action="store_true", help="probe company websites (robots-aware)")
    ss.add_argument("--site-budget", type=int, default=10)
    ss.add_argument("--no-peppol", action="store_true")
    ss.set_defaults(func=cmd_scan)

    sb = sub.add_parser("brief", help="generate Dutch briefings from scanned candidates")
    sb.add_argument("--limit", type=int, default=10)
    sb.add_argument("--params", default=str(ROOT / "params" / "rvo_wbso_2026.json"))
    sb.add_argument("--sender", default=str(ROOT / "params" / "sender_profile.example.json"))
    sb.add_argument("--candidates", default=None)
    sb.set_defaults(func=cmd_brief)

    sl = sub.add_parser("lint", help="re-lint generated briefings")
    sl.set_defaults(func=cmd_lint)

    sr = sub.add_parser("rescore", help="re-apply exclusion/scoring rules to an existing scan")
    sr.add_argument("--pushed-since", default="2026-02-01")
    sr.add_argument("--candidates", default=None)
    sr.set_defaults(func=cmd_rescore)

    srep = sub.add_parser("report", help="rebuild DRYRUN_REPORT.md from the existing run logs")
    srep.add_argument("--params", default=str(ROOT / "params" / "rvo_wbso_2026.json"))
    srep.set_defaults(func=lambda a: (write_dryrun_report(a), 0)[1])

    sd = sub.add_parser("dryrun", help="scan + brief + DRYRUN_REPORT.md")
    for arg in (
        ("--created-from", "2016-01-01"),
        ("--created-to", "2026-06-30"),
        ("--pushed-since", "2026-02-01"),
    ):
        sd.add_argument(arg[0], default=arg[1])
    sd.add_argument("--window-months", type=int, default=12)
    sd.add_argument("--max-orgs", type=int, default=60)
    sd.add_argument("--max-enriched", type=int, default=25)
    sd.add_argument("--budget", type=int, default=150)
    sd.add_argument("--fetch-sites", action="store_true")
    sd.add_argument("--site-budget", type=int, default=10)
    sd.add_argument("--no-peppol", action="store_true")
    sd.add_argument("--limit", type=int, default=10)
    sd.add_argument("--params", default=str(ROOT / "params" / "rvo_wbso_2026.json"))
    sd.add_argument("--sender", default=str(ROOT / "params" / "sender_profile.example.json"))
    sd.set_defaults(func=cmd_dryrun)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
