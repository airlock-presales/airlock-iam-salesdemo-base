import sys,re

def ind(l): return len(l)-len(l.lstrip(' '))

def step_range(L,step_id):
    k=[i for i,l in enumerate(L) if re.fullmatch(r' *id: '+re.escape(step_id),l)]
    assert len(k)==1,(step_id,k)
    i=k[0]-1; assert L[i].lstrip().startswith('- type:'),L[i]
    n=ind(L[i]); j=i+1
    while j<len(L) and (L[j].strip()=='' or ind(L[j])>n): j+=1
    return i,j

def cut_precondition(L,step_id):
    i,j=step_range(L,step_id)
    k=[x for x in range(i,j) if L[x].strip()=='preCondition:']; assert len(k)==1,(step_id,k)
    a=k[0]; n=ind(L[a]); b=a+1
    while b<len(L) and (L[b].strip()=='' or ind(L[b])>n): b+=1
    body=[l[n+2:] for l in L[a+1:b]]   # relative to the condition
    del L[a:b]
    return body

def deny_steps(n,prefix,name,cond_body,error='ACCESS_DENIED',message=True):
    """cond_body: lines of the condition relative to the 'skipCondition:' child indentation"""
    sp=' '*n
    def cond(lines): return [sp+'    skipCondition:']+[sp+'      '+l if l else l for l in lines]
    out=[]
    if message:
        out+=[sp+'- type: AcknowledgeMessageStep',sp+f'  id: {prefix}DeniedMessage',sp+f'  displayName: {name} - Access Denied (message)',
              sp+'  properties:',sp+'    messageId: access-denied']+cond(cond_body)
        ref=[l for l in cond_body if l.startswith('id: ')]
        cond_body=['ref: '+ref[0][4:]] if ref else cond_body
    out+=[sp+'- type: AbortStep',sp+f'  id: {prefix}DeniedAbort',sp+f'  displayName: {name} - Access Denied (abort, no failed attempt counted)',
          sp+'  properties:',sp+f'    errorCode: {error}']+cond(cond_body)
    return out

def insert_before(L,step_id,lines):
    i,_=step_range(L,step_id); L[i:i]=lines
