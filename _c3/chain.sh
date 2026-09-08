#!/bin/bash
cd /home/anont/meme/_c3
# wait for phase A (launched separately) to finish
until [ -f scores.json ] && [ scores.json -nt sweep.py ]; do sleep 5; done
echo "A done $(date +%T)" >> chain.log
python3 surface.py > surface.err 2>&1
echo "surface done $(date +%T)" >> chain.log
python3 sweepBC.py > sweepBC.err 2>&1
echo "B done $(date +%T)" >> chain.log
python3 sweepC.py > sweepC.err 2>&1
echo "C done $(date +%T)" >> chain.log
python3 validate.py > validate.err 2>&1
echo "V done $(date +%T)" >> chain.log
