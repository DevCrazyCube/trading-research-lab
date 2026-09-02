import json,sys
def build(idlf):
    d=json.load(open(idlf))
    prim={'u8':1,'u16':2,'u32':4,'u64':8,'u128':16,'i64':8,'i128':16,'bool':1,'pubkey':32}
    types={x['name']:x['type'] for x in d['types']}
    def size(ty):
        if isinstance(ty,str): return prim[ty]
        if 'array' in ty:
            e,n=ty['array']; return size(e)*n
        if 'defined' in ty:
            tt=types[ty['defined']['name']]
            if tt['kind']=='struct': return sum(size(f['type']) for f in tt['fields'])
            if tt['kind']=='enum': return 1
        raise Exception(str(ty))
    def offsets(name,base=8):
        tt=types[name]; off=base; out={}
        for f in tt['fields']:
            out[f['name']]=(off,f['type']); off+=size(f['type'])
        out['__end__']=(off,None)
        return out
    return offsets,size,d
if __name__=='__main__':
    offsets,size,d=build(sys.argv[1])
    o=offsets(sys.argv[2])
    for k,(off,ty) in o.items(): print(off,k,json.dumps(ty))
