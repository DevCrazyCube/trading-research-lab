#!/bin/bash
cd /home/anont/meme/_c3
until grep -q "^V done" chain.log 2>/dev/null; do sleep 10; done
python3 sweepC_liq.py > sweepCliq.err 2>&1
echo "LIQ done $(date +%T)" >> chain.log
