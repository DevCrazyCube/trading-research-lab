import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv

def roll(a,w,fn):
    n=a.size; out=np.full(n,np.nan)
    if n>=w:
        out[w-1:]=fn(swv(a,w),axis=-1)
    return out

def build_features(book):
    N=book.N
    F={}
    names=['vrel5','vrel20','vacc','rng','rngrel','dens10','dens30','gap','chop',
           'vwapdev','clspos','body','dvol','vshare','ret1','ret5','vzs','rngz','illiq','tickdir']
    for nm in names: F[nm]=np.full(N,np.nan)
    for mi in range(book.nm):
        s,e=book.starts[mi],book.ends[mi]
        ts=book.TS[s:e];O=book.O[s:e];HI=book.HI[s:e];LO=book.LO[s:e];C=book.C[s:e];V=book.V[s:e]
        n=e-s
        eps=1e-12
        Vp=np.maximum(V,eps)
        m5=roll(Vp,5,np.median); m20=roll(Vp,20,np.median)
        F['vrel5'][s:e]=Vp/m5
        F['vrel20'][s:e]=Vp/m20
        # vol acceleration: mean(last3)/mean(prior5)
        c3=roll(Vp,3,np.mean); c5=roll(Vp,5,np.mean)
        a=np.full(n,np.nan); 
        if n>8: a[7:]=c3[7:]/np.maximum(c5[4:n-3],eps)
        F['vacc'][s:e]=a
        rng=(HI-LO)/np.maximum(C,eps)
        F['rng'][s:e]=rng
        mr=roll(np.maximum(rng,1e-9),10,np.median)
        F['rngrel'][s:e]=rng/np.maximum(mr,1e-9)
        # trading density: real bars within trailing 10 / 30 minutes
        lo10=np.searchsorted(ts,ts-600.0,side='right'); lo30=np.searchsorted(ts,ts-1800.0,side='right')
        idx=np.arange(n)
        d10=(idx-lo10+1)/10.0; d30=(idx-lo30+1)/30.0
        # invalidate before enough elapsed history
        d10[ts-ts[0]<600]=np.nan; d30[ts-ts[0]<1800]=np.nan
        F['dens10'][s:e]=d10; F['dens30'][s:e]=d30
        g=np.full(n,np.nan); g[1:]=np.diff(ts)
        F['gap'][s:e]=g
        c2c=np.full(n,np.nan); c2c[1:]=np.abs(np.diff(C))
        F['chop'][s:e]=(HI-LO)/np.maximum(c2c,1e-9*C)
        typ=(HI+LO+C)/3.0
        pv=roll(typ*Vp,10,np.sum); vv=roll(Vp,10,np.sum)
        F['vwapdev'][s:e]=C/np.maximum(pv/np.maximum(vv,eps),eps)-1.0
        span=np.maximum(HI-LO,eps)
        F['clspos'][s:e]=(C-LO)/span
        F['body'][s:e]=np.abs(C-O)/span
        F['dvol'][s:e]=V
        F['vshare'][s:e]=Vp/np.maximum(vv,eps)
        r1=np.full(n,np.nan); r1[1:]=C[1:]/C[:-1]-1.0
        F['ret1'][s:e]=r1
        r5=np.full(n,np.nan)
        if n>5: r5[5:]=C[5:]/C[:-5]-1.0
        F['ret5'][s:e]=r5
        # log-volume z-score over 20
        lv=np.log(Vp)
        mu=roll(lv,20,np.mean); sd=roll(lv,20,np.std)
        F['vzs'][s:e]=(lv-mu)/np.maximum(sd,1e-6)
        lr=np.log(np.maximum(rng,1e-9))
        mu2=roll(lr,20,np.mean); sd2=roll(lr,20,np.std)
        F['rngz'][s:e]=(lr-mu2)/np.maximum(sd2,1e-6)
        # Amihud-style illiquidity: |ret1| / dollar volume
        F['illiq'][s:e]=np.abs(r1)/np.maximum(Vp,eps)
        # tick direction persistence: fraction of last 5 bars with C>O
        up=(C>O).astype(float)
        F['tickdir'][s:e]=roll(up,5,np.mean)
    return F
