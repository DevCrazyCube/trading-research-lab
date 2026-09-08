import pickle, statistics, sys
SCR='/home/anont/meme/.scr2'
S=pickle.load(open(SCR+'/surface.pkl','rb'))
structs=S['structs']; base=S['base']; mat=S['mat']; FIL=S['filters']
o=[]
def p(*a): o.append(" ".join(str(x) for x in a))
HOLDS=[2,5,15,30,60,180,480,1440]
MODS=['m_plain','m_tp30','m_tp50','m_tp100','m_tp200','m_tp400','m_sl20','m_sl35',
      'm_sl60','m_tr25','m_tr40','m_tp100sl50','m_half50']
idx={s:i for i,s in enumerate(structs)}
TARG=['burst300s>=2','burst600s>=2','burst1800s>=3','rate>=5/h','burst3600s>=5',
      'n>=3&gradrate>=0.05','nprior in[4,12]','nprior==0']
for f in TARG:
    j=FIL.index(f)
    for tn in ('first','allbars'):
        p("")
        p("### %s   timing=%s pos=p_single   cell = TRAINedge / VALIDedge  (edge vs same-structure unconditional)"%(f,tn))
        p("%-13s"%"mod"+"".join("%17s"%("h%d"%h) for h in HOLDS))
        ntr=0; nva=0; nb=0; both=0
        for mn in MODS:
            line="%-13s"%mn
            for h in HOLDS:
                k=(tn,'p_single',h,mn)
                i=idx.get(k)
                c=mat[i][j] if i is not None else None
                if c is None: line+="%17s"%"  --  "; continue
                trm,trk,vam,vamed,vak,vakc,van,vares,vm50,vm25,vraw,trkc=c
                te=trm-base[i][0]; ve=vam-base[i][1]
                nb+=1
                if te>0: ntr+=1
                if ve>0: nva+=1
                if te>0 and ve>0: both+=1
                line+="%17s"%("%+.3f/%+.3f"%(te,ve))
            p(line)
        p("  cells=%d  TRAINedge>0 in %d (%.2f)  VALIDedge>0 in %d (%.2f)  BOTH>0 in %d (%.2f)"%(
            nb,ntr,ntr/max(nb,1),nva,nva/max(nb,1),both,both/max(nb,1)))
open(SCR+'/plane.out','w').write("\n".join(o))
