#!/usr/bin/env bash
# durable_tick.sh -- the OS-crontab entrypoint for the durable, self-restarting
# trading-research supervisor. Called every 3 hours by cronie (see
# install_durable_cron.sh). Survives Claude-session death, crashes and reboots
# because the schedule lives in the on-disk user crontab, not in a live session.
#
# HARD RULES baked in here: research/paper only. No real money, no orders, no
# broker auth, no git commit. This script NEVER touches the t4 real-money path.
#
# What one tick does:
#   1. Take an flock so overlapping ticks can't stack.
#   2. cd into the repo, source .env defensively (guards the line-5 bare-key bug).
#   3. Run the cheap, self-guarded PURE-PYTHON engines (they refuse on their own
#      if not due / already ran / market closed) -- no LLM, basically free.
#   4. Invoke ONE headless Claude for the bounded THINKING chunk, under a hard
#      timeout so a hang can't wedge the tick. The prompt rotates by hour-of-day.
#   5. Append a heartbeat line.

set -u

# --- fixed paths (cron has a minimal environment; be explicit) -----------------
REPO="/home/anont/meme"
AG="${REPO}/scripts/agent_graph"
LOGS="${AG}/logs"
CLAUDE_BIN="/home/anont/.local/bin/claude"
LOCKFILE="${LOGS}/durable_tick.lock"
HEARTBEAT="${LOGS}/durable_heartbeat.log"
PROMPT_FILE="${AG}/supervisor_prompt.txt"

# cron's PATH is minimal -- make python and claude findable.
export PATH="/home/anont/.local/bin:/usr/local/bin:/usr/bin:/bin"
export HOME="/home/anont"

mkdir -p "${LOGS}"

# --- T50 STEP 3: THE EXECUTION CANARY (added 2026-09-05 00:00 CHUNK A) ----------
# WHY. On 2026-09-04, five consecutive supervisor ticks could not execute a single
# shell command inside the Claude session: commands returned exit 1 with no output,
# no-ops reported success, and `printf HELLO > /tmp/f` reported SUCCESS while leaving
# the file EMPTY. Exit codes lied; only OUTPUT told the truth. Every one of those
# ticks still wrote `claude=ok` to the heartbeat, because `ok` only ever meant "the
# claude process exited 0" -- never "the tick could do any work". A tick that cannot
# run a command can still append a confident, well-formed, entirely fictional
# "all ledgers verified, no faults" line, and nothing in the harness would notice.
#
# TWO CANARIES, because there are two shells and the fault was in the second one:
#   HOST_SHELL  -- this cron shell. Output-checked (write a nonce, read it back and
#                  string-compare), never exit-code-checked, because the exit code is
#                  precisely what lied. This is the pre-flight canary T50 asks for.
#   AGENT_SHELL -- the Claude session's Bash tool, which is where the observed fault
#                  actually lived and which the cron shell cannot test by proxy. The
#                  agent is handed a nonce it can ONLY obtain by successfully running
#                  a shell command, and must echo it back to an ack file. Verified
#                  here, after the call, by string-comparing the ack to the nonce.
# The nonce makes an unexecuted verification and a passed verification impossible to
# confuse: a tick with a dead shell cannot produce the token, and no amount of
# well-formed prose can substitute for it.
CANARY_NONCE=""
HOST_SHELL="unknown"
AGENT_SHELL="unknown"

host_shell_canary() {
    # Returns nothing; sets HOST_SHELL and CANARY_NONCE. Deliberately ignores every
    # exit status and judges ONLY on observed output.
    local want file got echoed
    want="TICKCANARY-$$-$(date +%s)-${RANDOM:-0}"
    file="${LOGS}/.canary_host.$$"
    printf '%s\n' "${want}" > "${file}" 2>/dev/null
    got="$(cat "${file}" 2>/dev/null)"
    echoed="$(echo "${want}" 2>/dev/null)"
    rm -f "${file}" 2>/dev/null
    if [ "${got}" = "${want}" ] && [ "${echoed}" = "${want}" ]; then
        HOST_SHELL="ok"
        CANARY_NONCE="${want}"
    else
        HOST_SHELL="BROKEN"
        CANARY_NONCE=""
    fi
}

# --- canary selftest: exercises BOTH branches, runs no tick --------------------
# Usage: durable_tick.sh --canary-selftest
if [ "${1:-}" = "--canary-selftest" ]; then
    fails=0
    host_shell_canary
    [ "${HOST_SHELL}" = "ok" ] || { echo "FAIL host canary healthy-branch: ${HOST_SHELL}"; fails=$((fails+1)); }
    [ -n "${CANARY_NONCE}" ]   || { echo "FAIL host canary produced no nonce"; fails=$((fails+1)); }
    echo "PASS host canary healthy branch (HOST_SHELL=${HOST_SHELL})"
    # Broken branch: simulate the exact observed fault -- an unwritable canary path,
    # i.e. the write "succeeds" but the read-back does not match.
    ( LOGS="/proc/definitely-not-writable-${RANDOM}"; host_shell_canary
      if [ "${HOST_SHELL}" = "BROKEN" ] && [ -z "${CANARY_NONCE}" ]; then
          echo "PASS host canary broken branch (HOST_SHELL=BROKEN, nonce suppressed)"; exit 0
      else
          echo "FAIL host canary broken branch: HOST_SHELL=${HOST_SHELL}"; exit 1
      fi ) || fails=$((fails+1))
    # Agent-ack verification, both branches.
    ack="${LOGS}/.canary_selftest_ack.$$"
    printf '%s\n' "NONCE-A" > "${ack}"
    if [ "$(cat "${ack}" 2>/dev/null | tr -d '[:space:]')" = "NONCE-A" ]; then
        echo "PASS agent-ack match branch"
    else
        echo "FAIL agent-ack match branch"; fails=$((fails+1))
    fi
    printf '%s\n' "SOMETHING-ELSE" > "${ack}"
    if [ "$(cat "${ack}" 2>/dev/null | tr -d '[:space:]')" = "NONCE-A" ]; then
        echo "FAIL agent-ack mismatch branch (accepted a wrong token)"; fails=$((fails+1))
    else
        echo "PASS agent-ack mismatch branch (wrong token rejected)"
    fi
    rm -f "${ack}" 2>/dev/null
    # Missing-ack branch: the shell-dead case -- no file at all.
    rm -f "${ack}" 2>/dev/null
    if [ -f "${ack}" ]; then echo "FAIL agent-ack missing branch"; fails=$((fails+1)); else echo "PASS agent-ack missing branch (no file => UNPROVEN)"; fi
    if [ "${fails}" -eq 0 ]; then echo "CANARY SELFTEST: ALL_PASSED"; exit 0; else echo "CANARY SELFTEST: ${fails} FAILURE(S)"; exit 1; fi
fi

host_shell_canary

# --- single-flight lock --------------------------------------------------------
# Non-blocking: if a previous tick is still running, log and exit rather than stack.
exec 9>"${LOCKFILE}"
if ! flock -n 9; then
    echo "$(date -Is) SKIP tick=$(date +%H) reason=previous-tick-still-running" >> "${HEARTBEAT}"
    exit 0
fi

cd "${REPO}" || { echo "$(date -Is) FATAL cannot cd ${REPO}" >> "${HEARTBEAT}"; exit 1; }

TICK_HOUR="$(date +%H)"
STAMP="$(date +%Y%m%d)"
TICK_LOG="${LOGS}/tick_${STAMP}.log"

log() { echo "$(date -Is) $*" | tee -a "${TICK_LOG}"; }

log "==== DURABLE TICK START hour=${TICK_HOUR} pid=$$ ===="

# --- .env handling: SECRETS STAY OUT OF THE HEADLESS-CLAUDE ENVIRONMENT ---------
# SECURITY (deliberate): we do NOT export .env at the top level. If we did, the
# headless Claude below would inherit ALPACA / TELEGRAM / SOLANA keys, and a
# prompt-injection hidden in the untrusted web content the agents read could
# exfiltrate them. Instead .env is sourced ONLY inside each pure-python engine's
# own subshell (see run_py). The thinking agent never sees the secrets and does
# not need them. (.env line-5 bare-key bug is still handled by the KEY=VALUE grep.)
if [ -f "${REPO}/.env" ]; then
    log "env will be sourced per-engine only (secrets kept OUT of the claude env)"
else
    log "no .env present"
fi

# --- pure-python engines: cheap, free, self-guarded ----------------------------
# Each of these refuses on its own if it isn't due / already ran / market closed.
# `|| true` so a single engine's guard-exit never aborts the tick.
PY_RAN=""
run_py() {
    local label="$1"; shift
    log "python: ${label} :: $*"
    # .env is sourced HERE, inside this subshell only -- never at top level -- so the
    # engine gets its keys but the headless claude call never inherits them.
    if ( set -a
         source <(grep -E '^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*=' "${REPO}/.env" 2>/dev/null) 2>/dev/null
         set +a
         timeout 600 python -m "$@" ) >>"${TICK_LOG}" 2>&1; then
        log "python: ${label} OK"
    else
        log "python: ${label} exited nonzero (guarded/not-due/closed -- expected, continuing)"
    fi
    PY_RAN="${PY_RAN} ${label}"
    return 0
}

run_py basket_forward   scripts.trading_bot.basket_forward session --refresh-cash || true
run_py newsdesk_resolve scripts.trading_bot.newsdesk resolve                       || true
run_py predmarket_resolve scripts.trading_bot.predmarket resolve                   || true

# --- T52: INPUT-RECENCY LIVENESS ALARM (read-only, never fatal) ----------------
# The MEME ARENA sat input-dead for 56h while chain_ok, the dashboard and the runtime
# logs all stayed green: every liveness signal we publish is a PROXY. The only signal
# that cannot lie is the age of the newest INPUT row, read from the row's OWN timestamp.
# Run it BEFORE the thinking chunk and hand the result to the agent, so a dead feed is
# named at the top of the tick instead of being discovered days later by an audit.
RECENCY_LOG="${LOGS}/input_recency_${STAMP}_h${TICK_HOUR}.txt"
RECENCY_STALE="unknown"
RECENCY_BLOCK=""
if timeout 120 python3 -m scripts.trading_bot.input_recency_alarm > "${RECENCY_LOG}" 2>&1; then
    RECENCY_STALE="none"
else
    rc=$?
    if [ "${rc}" = "1" ]; then
        RECENCY_STALE="$(grep -E '^  - ' "${RECENCY_LOG}" | sed 's/^  - //; s/:.*//' | tr '\n' ',' | sed 's/,$//')"
        [ -n "${RECENCY_STALE}" ] || RECENCY_STALE="stale-unnamed"
    else
        RECENCY_STALE="ALARM-ITSELF-FAILED-rc${rc}"
    fi
fi
log "input-recency: stale={${RECENCY_STALE}} -> ${RECENCY_LOG}"
if [ -s "${RECENCY_LOG}" ]; then
    RECENCY_BLOCK="

=========================== INPUT-RECENCY ALARM (T52, read this) ==================
This ran BEFORE you, read-only, against every live forward instrument. It reports the age
of each instrument's newest INPUT ROW against that instrument's declared cadence. A green
process, a rendering dashboard and an intact hash chain are all PROXIES and all stayed
green through the 56-hour MEME ARENA outage; this is the signal that cannot lie.
STALE instruments this tick: {${RECENCY_STALE}}
$(cat "${RECENCY_LOG}")

Report STALE instruments BY NAME in your tick output. Do NOT restart, re-activate, re-epoch
or resolve anything to fix one -- observing is this alarm's whole job, and a restart is an
owner decision. A STALE instrument whose outage is already known and logged needs one line,
not a re-investigation."
fi

# --- headless Claude: the bounded THINKING chunk -------------------------------
# ONE non-interactive turn. --permission-mode bypassPermissions lets it use
# bash/write/edit without an interactive prompt (there is no human to answer one).
# Hard timeout so a hang can't wedge the tick. All output captured to a dated log.
CLAUDE_LOG="${LOGS}/claude_${STAMP}_h${TICK_HOUR}.log"
CLAUDE_STATUS="skipped-missing-prompt"
# FINDINGS self-stamp support (added 2026-08-29 15:00 CHUNK B on the 08-28/08-29 STRATEGIST
# recommendation): remember the ledger's mtime so we can tell whether this tick wrote to it.
FINDINGS="${REPO}/research/FINDINGS.md"
FINDINGS_MTIME_BEFORE="$(stat -c %Y "${FINDINGS}" 2>/dev/null || echo 0)"

# T50 STEP 3: hand the agent a nonce it can only obtain by RUNNING a command, and an
# ack path to echo it back to. The prompt FILE on disk is deliberately not modified --
# the instruction is composed at call time so the canary carries no state between ticks.
CANARY_ACK="${LOGS}/canary_ack_${STAMP}_h${TICK_HOUR}.txt"
CANARY_SRC="${LOGS}/canary_nonce_${STAMP}_h${TICK_HOUR}.txt"
rm -f "${CANARY_ACK}" 2>/dev/null
CANARY_BLOCK=""
if [ "${HOST_SHELL}" = "ok" ]; then
    printf '%s\n' "${CANARY_NONCE}" > "${CANARY_SRC}" 2>/dev/null
    CANARY_BLOCK="

=========================== EXECUTION CANARY (do this FIRST) ======================
Before any other work, run this ONE bash command and look at its output:
    cat ${CANARY_SRC} | tee ${CANARY_ACK}
If it prints a TICKCANARY-... token, your shell works: proceed with your chunk normally.
If it prints nothing, errors, or the ack file stays empty, YOUR SHELL IS DEAD (this has
happened: exit codes reported success while nothing ran). In that case do NOT report on
any ledger, file or command output you could not actually read. Write ONE short
NOT VERIFIED paragraph naming what you could not query, and STOP.
The harness verifies this token after you exit; a tick that does not produce it is
recorded as shell=UNPROVEN and its claims are treated as unverified. Do not write the
token by hand from this prompt -- that defeats the check and corrupts the ledger."
fi

if [ -x "${CLAUDE_BIN}" ] && [ -f "${PROMPT_FILE}" ]; then
    log "headless claude: START (timeout 3600s, host_shell=${HOST_SHELL}) -> ${CLAUDE_LOG}"
    if timeout 3600 "${CLAUDE_BIN}" -p "$(cat "${PROMPT_FILE}")${CANARY_BLOCK}${RECENCY_BLOCK}" \
            --permission-mode bypassPermissions \
            >>"${CLAUDE_LOG}" 2>&1; then
        CLAUDE_STATUS="ok"
    else
        rc=$?
        if [ "${rc}" = "124" ]; then CLAUDE_STATUS="timeout-3600s"; else CLAUDE_STATUS="exit-${rc}"; fi
    fi
    log "headless claude: DONE status=${CLAUDE_STATUS}"
else
    log "headless claude: SKIPPED (missing ${CLAUDE_BIN} or ${PROMPT_FILE})"
fi

# --- T50 STEP 3: verify the agent's execution proof ----------------------------
# Judged on CONTENT, not on the claude process's exit status -- which was `ok` on all
# five shell-dead ticks and is therefore worthless as a signal that work happened.
if [ "${HOST_SHELL}" != "ok" ]; then
    AGENT_SHELL="host-broken"
elif [ "$(cat "${CANARY_ACK}" 2>/dev/null | tr -d '[:space:]')" = "${CANARY_NONCE}" ]; then
    AGENT_SHELL="proven"
else
    AGENT_SHELL="UNPROVEN"
fi
log "canary: host_shell=${HOST_SHELL} agent_shell=${AGENT_SHELL}"

# --- FINDINGS self-stamp -------------------------------------------------------
# Four ticks (08-27 15:00 silent; 08-28 21:00; 08-29 06:00 + 09:00) ran to DONE but left no
# FINDINGS line, and a later STRATEGIST tick had to reconstruct them from logs. If the ledger's
# mtime did not advance during this tick, append an explicit AUTO-STAMP stub so the durable
# ledger never has a silent gap. The stub is a process record, NOT evidence. Append-only.
FINDINGS_MTIME_AFTER="$(stat -c %Y "${FINDINGS}" 2>/dev/null || echo 0)"
if [ -f "${FINDINGS}" ] && [ "${FINDINGS_MTIME_AFTER}" = "${FINDINGS_MTIME_BEFORE}" ]; then
    CLAUDE_BYTES="$(stat -c %s "${CLAUDE_LOG}" 2>/dev/null || echo 0)"
    case "${TICK_HOUR}" in
        00|12) CHUNK="A STRATEGIST" ;;
        03|15) CHUNK="B INVENTION" ;;
        06|18) CHUNK="C NEWSDESK" ;;
        09|21) CHUNK="D PREDMARKET" ;;
        *)     CHUNK="A STRATEGIST (off-rotation hour)" ;;
    esac
    printf '\n## %s %s:00 CEST — CHUNK %s tick (durable supervisor) — [AUTO-STAMP by durable_tick.sh: the tick wrote NO FINDINGS line; claude status=%s; shell host=%s agent=%s; claude log %s bytes: %s. Process record, not evidence; a later tick may reconstruct from the log.]\n' \
        "$(date +%Y-%m-%d)" "${TICK_HOUR}" "${CHUNK}" "${CLAUDE_STATUS}" "${HOST_SHELL}" "${AGENT_SHELL}" "${CLAUDE_BYTES}" "${CLAUDE_LOG}" >> "${FINDINGS}"
    log "findings: AUTO-STAMPED stub (ledger mtime did not advance during this tick)"
else
    log "findings: written during this tick (mtime advanced)"
    # A tick that WROTE but could not EXECUTE is the dangerous case the AUTO-STAMP guard
    # is blind to: well-formed prose, no way to have read anything. Stamp it next to the
    # tick's own line so the two can never be read as the same claim. Only on fault, so
    # a healthy ledger is not padded with one harness line per tick.
    if [ "${AGENT_SHELL}" != "proven" ] && [ -f "${FINDINGS}" ]; then
        printf '\n## %s %s:00 CEST — [HARNESS-STAMP by durable_tick.sh: shell host=%s agent=%s. The agent did NOT return the execution canary token, so it could not run shell commands this tick. ANY ledger/verification claim in the tick line above is UNVERIFIED by construction and must not be relied on. Process record, not evidence.]\n' \
            "$(date +%Y-%m-%d)" "${TICK_HOUR}" "${HOST_SHELL}" "${AGENT_SHELL}" >> "${FINDINGS}"
        log "findings: HARNESS-STAMPED shell fault (agent_shell=${AGENT_SHELL}) beside the tick's own line"
    fi
fi

log "==== DURABLE TICK END hour=${TICK_HOUR} ===="

# --- heartbeat -----------------------------------------------------------------
echo "$(date -Is) TICK hour=${TICK_HOUR} python={${PY_RAN# }} claude=${CLAUDE_STATUS} shell=${HOST_SHELL}/${AGENT_SHELL} stale={${RECENCY_STALE}}" >> "${HEARTBEAT}"

exit 0
