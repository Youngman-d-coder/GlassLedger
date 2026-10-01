import re
ACRONYMS={'edta':'EDTA','vdrl':'VDRL','aso':'ASO','rf':'RF','n95':'N95','a4':'A4','hiv':'HIV','esr':'ESR','mp':'MP'}
def clean_spaces(v): return re.sub(r'\s+',' ',(v or '').strip())
def normalize_name(v):
    parts=[]
    for token in clean_spaces(v).split(' '):
        low=token.lower()
        if low in ACRONYMS: parts.append(ACRONYMS[low])
        elif low in {'ml','mls'}: parts.append('mL')
        else: parts.append(token[:1].upper()+token[1:].lower() if token else token)
    return ' '.join(parts)
def slugify(v): return re.sub(r'[^a-z0-9]+','-',clean_spaces(v).lower()).strip('-')
def normalize_note(v): return clean_spaces(v)
