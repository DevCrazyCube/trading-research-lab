import hashlib
A='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
def b58d(s):
    n=0
    for c in s: n=n*58+A.index(c)
    b=n.to_bytes((n.bit_length()+7)//8,'big')
    pad=len(s)-len(s.lstrip('1'))
    return b'\0'*pad+b
def b58e(b):
    n=int.from_bytes(b,'big'); s=''
    while n: n,r=divmod(n,58); s=A[r]+s
    pad=len(b)-len(b.lstrip(b'\0'))
    return '1'*pad+s
P=2**255-19
D=(-121665*pow(121666,P-2,P))%P
I=pow(2,(P-1)//4,P)
def on_curve(b):
    y=int.from_bytes(b,'little'); sign=(y>>255)&1; y&=(1<<255)-1
    if y>=P: return False
    yy=y*y%P
    u=(yy-1)%P; v=(D*yy+1)%P
    x=u*pow(v,(P-5)//8,P)*pow(v,3,P)%P  # candidate via v^3*u*(uv^7)^((p-5)/8) simplified
    # standard: x = u*v^3 * (u*v^7)^((p-5)/8)
    x=(u*pow(v,3,P))%P*pow((u*pow(v,7,P))%P,(P-5)//8,P)%P
    if (v*x*x-u)%P==0: pass
    elif (v*x*x+u)%P==0: x=x*I%P
    else: return False
    return True
def find_pda(seeds, program):
    pid=b58d(program)
    for bump in range(255,-1,-1):
        h=hashlib.sha256()
        for s in seeds: h.update(s)
        h.update(bytes([bump])); h.update(pid); h.update(b'ProgramDerivedAddress')
        d=h.digest()
        if not on_curve(d): return b58e(d),bump
    raise Exception('no pda')
def create_with_seed(base, seed, owner):
    h=hashlib.sha256(); h.update(b58d(base)); h.update(seed.encode()); h.update(b58d(owner))
    return b58e(h.digest())
def idl_addr(program):
    base,_=find_pda([],program)
    return create_with_seed(base,'anchor:idl',program)
