import sys,pickle,collections
sys.path.insert(0,'/home/anont/meme/research/midcap/fv3')
import numpy as np
W='/home/anont/meme/research/midcap/fv3/'
out=open(W+'SUMMARY.txt','w')
tot=0
try:
    B=pickle.load(open(W+'stageB.pkl','rb'))
    out.write('stageB combos=%d train-positive=%d\n'%(B['combos'],len(B['keep'])))
    tot+=B['combos']
except Exception as e: out.write('stageB missing %s\n'%e)
try:
    C=pickle.load(open(W+'stageC.pkl','rb'))
    out.write('stageC total combos=%d train-positive=%d\n'%(C['combos'],len(C['ALLTR'])))
    tot=max(tot,C['combos'])
except Exception as e: out.write('stageC missing %s\n'%e)
try:
    D=pickle.load(open(W+'stageD.pkl','rb'))
    out.write('validate survivors=%d\n'%len(D['surv']))
except Exception as e: out.write('stageD missing %s\n'%e)
try:
    G=pickle.load(open(W+'stageG.pkl','rb'))
    out.write('greedy combos=%d\n'%G['combos']); tot+=G['combos']
except Exception as e: out.write('stageG missing %s\n'%e)
out.write('TOTAL_COMBOS_APPROX=%d\n'%tot)
out.close()
print(open(W+'SUMMARY.txt').read())
