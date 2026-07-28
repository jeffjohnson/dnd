import re, json
_D=open('/home/claude/addgraph/dmg.doctags').read()
_PAGES=_D.split('<page_break>')

def _otsl(body):
    body=re.sub(r'<loc_\d+>','',body)
    cells=re.findall(r'<(fcel|ecel|ched|rhed|srow|nl)>([^<]*)', body)
    rows=[]; cur=[]
    for t,v in cells:
        if t=='nl': rows.append(cur); cur=[]
        elif t=='srow': cur.append(f"[{v.strip()}]")
        else: cur.append(v.strip())
    if cur: rows.append(cur)
    return "\n".join(" | ".join(r) for r in rows if any(x for x in r))

def text(pg):
    p=_PAGES[pg]; out=[]
    for m in re.finditer(r'<(text|section_header_level_\d|list_item|otsl|page_header|caption)>(.*?)</\1>', p, re.S):
        kind, body = m.group(1), m.group(2)
        if kind=='otsl': out.append(_otsl(body))
        else:
            b=re.sub(r'<[^>]+>','',body).strip()
            if b: out.append(("## "+b) if kind.startswith('section_header') else b)
    return "\n".join(out)

def dehyphen(s):
    return re.sub(r'(\w)-\s+(\w)', r'\1\2', s)

def find(kw):
    kw=kw.lower()
    return [i for i,p in enumerate(_PAGES) if kw in dehyphen(re.sub(r'<[^>]+>',' ',p)).lower()]

def headers(pg):
    return [re.sub(r'<[^>]+>','',m).strip() for m in
            re.findall(r'<section_header_level_\d>(.*?)</section_header_level_\d>', _PAGES[pg], re.S)]

def tables(pg): return len(re.findall(r'<otsl>', _PAGES[pg]))
def words(pg): return len(text(pg).split())

def status(minwords=120):
    import csv
    from collections import Counter
    master=list(csv.DictReader(open('/home/claude/addgraph/edges_master.csv')))
    cited=Counter(e['page'] for e in master if e['book']=='DMG')
    rows=[]
    for pg in range(9, min(241,len(_PAGES))):
        w=words(pg)
        if w<minwords: continue
        n=cited.get(str(pg),0)
        d=n/w*1000
        rows.append({'pg':pg,'words':w,'tables':tables(pg),'edges':n,'per1k':round(d,1),
                     'state':'DONE' if d>=10 else ('THIN' if n>0 else 'TODO'),
                     'head':(headers(pg)[0][:44] if headers(pg) else '')})
    return rows
