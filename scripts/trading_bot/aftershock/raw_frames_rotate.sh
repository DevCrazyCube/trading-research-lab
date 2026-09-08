#!/bin/sh
# raw_frames_rotate.sh — emergency disk containment for the pac_lws raw_frames log.
# Installed by the durable supervisor 2026-09-01 15:00 CEST as the T44 stopgap:
# pac_lws_feed.py instantiates b15i.RawLog with defaults (no self-rotation, no
# free-space guard), so raw_frames.jsonl grows unbounded (~38 GB/day measured).
# This script seals the file to zstd segments (evidence preserved, ~10:1) and
# copytruncates, exactly the procedure of the 12:00 incident triage. It NEVER
# truncates unless both seal segments pass `zstd -t`. Real fix = T44 (wire
# RawLog retention into the feed via a deliberate stamped restart, Codex lane);
# remove this cron entry when T44 lands.
set -u
FILE=/home/anont/meme/research/data/aftershock/pac_lws/raw_frames.jsonl
DIR=$(dirname "$FILE")
LOG="$DIR/rotate.log"
THRESH=$((2 * 1024 * 1024 * 1024))   # rotate above 2 GiB

[ -f "$FILE" ] || exit 0
S0=$(stat -c%s "$FILE")
[ "$S0" -ge "$THRESH" ] || exit 0

TS=$(date +%Y%m%dT%H%M%S)
SEG_A="$DIR/raw_frames.rot_${TS}a.jsonl.zst"
SEG_B="$DIR/raw_frames.rot_${TS}b.jsonl.zst"

# Pass 1: seal the first S0 bytes (whole frames; writer is O_APPEND so bytes
# 1..S0 are immutable).
head -c "$S0" "$FILE" | zstd -q -o "$SEG_A" || { echo "$(date -Is) FAIL pass1" >> "$LOG"; exit 1; }
zstd -t -q "$SEG_A" || { echo "$(date -Is) FAIL verify-a" >> "$LOG"; exit 1; }

# Pass 2: seal what was appended while pass 1 ran.
S1=$(stat -c%s "$FILE")
if [ "$S1" -gt "$S0" ]; then
    tail -c +"$((S0 + 1))" "$FILE" | head -c "$((S1 - S0))" | zstd -q -o "$SEG_B" \
        || { echo "$(date -Is) FAIL pass2" >> "$LOG"; exit 1; }
    zstd -t -q "$SEG_B" || { echo "$(date -Is) FAIL verify-b" >> "$LOG"; exit 1; }
fi

# Seam: bytes appended between the pass-2 read and the truncate are lost.
# Measured byte-exact below (seam <= S2 - S1); historically ~KB per rotation.
S2=$(stat -c%s "$FILE")
truncate -s 0 "$FILE"
echo "$(date -Is) rotated sealed=$S0+$((S1 - S0)) seam_max=$((S2 - S1)) free_kb=$(df --output=avail / | tail -1 | tr -d ' ')" >> "$LOG"
