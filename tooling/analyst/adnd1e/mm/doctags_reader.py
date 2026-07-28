"""Column-aware Monster Manual reader. Recovers reading order from bounding boxes."""
import re
_D=open('/home/claude/addgraph/mm.doctags').read()
_PAGES=_D.split('<page_break>')

def elements(pg):
    """Return page elements as (col, y, kind, text), in true reading order."""
    out=[]
    for m in re.finditer(r'<(section_header_level_\d|text|otsl|list_item|page_footer)>'
                         r'<loc_(\d+)><loc_(\d+)><loc_(\d+)><loc_(\d+)>(.*?)</\1>', _PAGES[pg], re.S):
        kind,x1,y1,x2,y2,body = m.group(1),int(m.group(2)),int(m.group(3)),int(m.group(4)),int(m.group(5)),m.group(6)
        if kind=='page_footer': continue
        col = 0 if x1 < 150 else 1
        if kind=='otsl':
            b=re.sub(r'<loc_\d+>','',body)
            cells=re.findall(r'<(fcel|ecel|ched|rhed|srow|nl)>([^<]*)', b)
            rows=[];cur=[]
            for t,v in cells:
                if t=='nl': rows.append(cur); cur=[]
                else: cur.append(v.strip())
            if cur: rows.append(cur)
            txt="\n".join(" | ".join(r) for r in rows if any(r))
        else:
            txt=re.sub(r'<[^>]+>','',body).strip()
        if txt and 'Jeff Johnson' not in txt:
            out.append((col,y1,kind,txt))
    return sorted(out, key=lambda e:(e[0],e[1]))

def entries(pg):
    """Monster entries on a page: (name, statblock_text, prose)."""
    els=elements(pg); res=[]; cur=None
    for col,y,kind,txt in els:
        if kind.startswith('section_header'):
            if cur: res.append(cur)
            cur={'name':txt,'stat':'','prose':''}
        elif cur is not None:
            if 'FREQUENCY' in txt: cur['stat'] += txt+"\n"
            else: cur['prose'] += txt+"\n"
    if cur: res.append(cur)
    return [r for r in res if r['stat']]

def allpages(): return range(len(_PAGES))
