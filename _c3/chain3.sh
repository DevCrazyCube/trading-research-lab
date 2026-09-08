#!/bin/bash
cd /home/anont/meme/_c3
python3 sweepC.py > sweepC.err 2>&1
echo "C done $(date +%T)" >> chain.log
python3 validate.py > validate.err 2>&1
echo "V done $(date +%T)" >> chain.log
