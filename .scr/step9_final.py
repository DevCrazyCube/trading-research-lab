import numpy as np, sys, pickle, hashlib
sys.path.insert(0,'/home/anont/meme/.scr')
from sim import *
G=pickle.load(open(SCR+'gated.pkl','rb')); out=G['out']
V=pickle.load(open(SCR+'validated.pkl','rb')); out2=V['out']
print('HOLDOUT CHECK: any h==0 mint in the working set?',
      any(int(hashlib.md5(m.encode()).hexdigest(),16)%3==0 for m in MINTS))
print('mints used:',len(MINTS),'train(h=1)',len(TRAIN),'validate(h=2)',len(VALD))
vm=np.array([o['vmean'] for o in out])
print(f'\nGATED (fillable) candidates validated: {len(out)}')
print(f'  best validate mean = {vm.max()*100:+.2f}%  worst = {vm.min()*100:+.2f}%  median = {np.median(vm)*100:+.2f}%')
print(f'  count with validate mean > 0: {int((vm>0).sum())}')
vm2=np.array([o['vmean'] for o in out2]); vmed2=np.array([o['vmed'] for o in out2])
print(f'\nUNGATED candidates validated: {len(out2)}')
print(f'  count with validate mean>0 AND validate median>0: {int(((vm2>0)&(vmed2>0)).sum())}')
print(f'  best validate median = {vmed2.max()*100:+.2f}%')
# combos accounting
print('\nCOMBO ACCOUNTING')
tot=1560+41040+41250+400+G['nsw']+len(out)+360+14
print('  1-way screen (26 feat x 6 thr x 10 exits)      : 1560')
print('  3-way ungated  entry x exit                    : 41040')
print('  3-way ungated  full exit x position grid       : 41250')
print('  3-way ungated  validate pass                   : 400')
print('  3-way GATED    entry x exit                    :',G['nsw'])
print('  3-way GATED    validate pass                   :',len(out))
print('  structure-matched controls                     : ~374')
print('  TOTAL evaluations                              :',tot)
print('  (+ 4000 matched random-entry placebo draws, + 400x4000 cluster bootstrap resamples)')
