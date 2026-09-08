s=open('/home/anont/meme/_c3/placebo.py').read()
s=s.replace("STORE={}\n","")
s=s.replace("if r: PC.append(r); STORE[(d,ci)]=m","if r: PC.append(r)")
s=s.replace("    m=STORE[(r['desc'],r['ci'])]; ci=r['ci']",
            "    m=mask_of(r['desc']); ci=r['ci']")
s=s.replace("PRE=[r for r in PC if r['edge']>0",
 "def mask_of(desc):\n"
 "    m=np.ones(N,bool)\n"
 "    for d in desc:\n"
 "        k,v=d.split('=')\n"
 "        if k in MF: b,_=MF[k]; m&=(b==int(v))\n"
 "        else: b,_=B4[k]; m&=(b==int(v[1:]))\n"
 "    return m\n"
 "PRE=[r for r in PC if r['edge']>0",1)
open('/home/anont/meme/_c3/placebo.py','w').write(s)
open('/home/anont/meme/_c3/fix.out','w').write("STORE_left=%s mask_of=%d\n"%("STORE" in s, s.count("mask_of")))
