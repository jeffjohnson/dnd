"""Read-only source/graph audit; writes diagnostic JSON only when --output is given."""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text(x):
    if isinstance(x, list):
        return ''.join(text(y) for y in x)
    if not isinstance(x, dict):
        return ''
    if x.get('t') == 'Str':
        return x['c']
    if x.get('t') in ('Space', 'SoftBreak', 'LineBreak'):
        return ' '
    return text(x.get('c', []))


def norm(s):
    return re.sub('[^a-z0-9]', '', unicodedata.normalize('NFKD', s).casefold())


def inventory(relative):
    path = ROOT / relative
    ast = json.loads(subprocess.check_output(
        ['pandoc', '-f', 'markdown', '-t', 'json', str(path)], text=True, encoding='utf-8'))
    rows = []
    current_class = None
    tier = None
    headings = {'PRIEST SPELLS LIST': 'class_priest', 'WIZARD SPELL LIST': 'class_wizard',
                'WITCH SPELL LIST': 'class_witch', 'SEER SPELL LIST': 'class_seer'}
    for index, block in enumerate(ast['blocks']):
        if block['t'] == 'Header':
            title = text(block['c'][2]).upper()
            if title == 'SUPPORTING SOURCE CONTEXT':
                break
            if title in headings:
                current_class = headings[title]
                tier = None
            elif re.fullmatch(r'TIER [1-5]', title):
                tier = int(title[-1])
            elif block['c'][0] <= 2:
                current_class = None
                tier = None
        if block['t'] == 'BulletList' and current_class and tier:
            for item in block['c']:
                rows.append({'name': text(item), 'class_id': current_class, 'tier': tier,
                             'source_file': relative, 'pandoc_block': index})
    return rows


def run():
    canonical = ROOT / 'rulesets/shadowdark/canonical'
    graph = json.loads((canonical / 'graph.json').read_text(encoding='utf-8'))
    nodes = {n['id']: n for n in graph['nodes']}
    edges = graph['edges']
    csv_edges = list(csv.DictReader((canonical / 'edges_master.csv').open(encoding='utf-8-sig', newline='')))
    csv_nodes = list(csv.DictReader((canonical / 'nodes_master.csv').open(encoding='utf-8-sig', newline='')))
    paths = {'SD': 'books/shadowdark/sd/packets/incoming/019-priest-and-wizard-spell-lists.md',
             'CS1': 'books/shadowdark/cs1/packets/incoming/cs1.21-38.md',
             'CS3': 'books/shadowdark/cs3/packets/incoming/cs3.29-36.md'}
    by_label = collections.defaultdict(list)
    for n in nodes.values():
        if n.get('kind') == 'spell':
            by_label[norm(n['label'])].append(n['id'])
    # Explicit audit comparison alias, not a canonical registration or rename.
    aliases = {'judgment': 'spell_judgement'}
    resolved = {}
    for book, relative in paths.items():
        rows = inventory(relative)
        missing, missing_scoped, wrong_tiers = [], [], []
        for row in rows:
            key = norm(row['name'])
            matches = by_label.get(key, [])
            if not matches and aliases.get(key) in nodes:
                matches = [aliases[key]]
                row['audit_alias'] = True
            row['resolved_ids'] = matches
            if len(matches) != 1:
                continue
            sid = matches[0]
            matching = [e for e in edges if e['source_id'] == sid and
                        e['edge_type'] == 'CLASSIFIED_AS' and e['target_id'] == row['class_id']]
            if not matching:
                missing.append(row)
            if not any(e.get('book') == book for e in matching):
                missing_scoped.append(row)
            if not any(e['source_id'] == sid and e['edge_type'] == 'CLASSIFIED_AS' and
                       e['target_id'] == f"rule_spell_tier_{row['tier']}" for e in edges):
                wrong_tiers.append(row)
        ids = {r['resolved_ids'][0] for r in rows if len(r['resolved_ids']) == 1}
        expected = {(r['resolved_ids'][0], r['class_id']) for r in rows if len(r['resolved_ids']) == 1}
        extras = [dict(e, csv_line=i+2) for i,e in enumerate(csv_edges)
                  if e['book'] == book and e['source_id'] in ids and e['edge_type'] == 'CLASSIFIED_AS'
                  and e['target_id'].startswith('class_') and (e['source_id'],e['target_id']) not in expected]
        mechanical = {e[k] for e in edges if e['edge_type'] != 'CLASSIFIED_AS' for k in ('source_id','target_id')}
        resolved[book] = {'entry_count': len(rows), 'unique_nodes': len(ids), 'rows': rows,
                          'missing_class_memberships': missing, 'missing_book_scoped_memberships': missing_scoped,
                          'missing_expected_tier': wrong_tiers, 'extra_scoped_class_edges': extras,
                          'no_incident_nonclassification_edges': sorted(ids-mechanical)}
    def comparable(rows, keys):
        return collections.Counter(tuple(str(r.get(k,'')) for k in keys) for r in rows)
    node_keys = list(csv_nodes[0]); edge_keys = list(csv_edges[0])
    baseline = ROOT / 'build/snapshots/INT-20261104-BASE/graph.json'
    base = json.loads(baseline.read_text(encoding='utf-8')) if baseline.exists() else None
    neighbors = {n:set() for n in nodes}
    dangling=[]
    for e in edges:
        a,b=e['source_id'],e['target_id']
        if a not in nodes or b not in nodes: dangling.append(e);continue
        neighbors[a].add(b);neighbors[b].add(a)
    unseen=set(nodes); sizes=[]
    while unseen:
        stack=[unseen.pop()];count=0
        while stack:
            n=stack.pop();count+=1
            nxt=neighbors[n]&unseen;unseen-=nxt;stack.extend(nxt)
        sizes.append(count)
    files=[canonical/'graph.json',canonical/'nodes_master.csv',canonical/'edges_master.csv']+[ROOT/p for p in paths.values()]
    sys.path.insert(0, str(ROOT / 'tooling/builder/src'))
    from adnd1e_builder.rules_retrieval import RulesRetrievalEngine
    from adnd1e_builder.manifest_gate import SourceEntityManifestGate
    empty = RulesRetrievalEngine()
    live = RulesRetrievalEngine(str(canonical / 'graph.json'))
    probes = {name: getattr(empty, name)() == getattr(live, name)() for name in (
        'query_wizard_sleep_in_plate', 'query_wizard_greatsword', 'query_focus_damage',
        'query_dying_rules', 'query_priest_burning_hands', 'query_dnd5e_edition_isolation',
        'query_unproficient_weapon_use', 'query_reference_only_node')}
    run_tests = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s',
        'tooling/reviewer/tests', '-p', 'test_remediation_regressions.py', '-v'],
        cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    return {'scope_note':'Local packet-list and structural validation only; not full semantic certification.',
            'empty_graph_matches_live_answers':probes,
            'empty_manifest_accepted':SourceEntityManifestGate().validate_packet_entities(set()),
            'existing_tests':{'command':'python -m unittest discover -s tooling/reviewer/tests -p test_remediation_regressions.py -v',
                              'exit_code':run_tests.returncode,'transcript':run_tests.stdout+run_tests.stderr},
            'hashes':{p.relative_to(ROOT).as_posix():sha(p) for p in files},
            'graph':{'nodes':len(nodes),'edges':len(edges),'top_level_keys':list(graph),
                     'csv_node_fields':node_keys,'csv_edge_fields':edge_keys,
                     'node_csv_parity':comparable(csv_nodes,node_keys)==comparable(graph['nodes'],node_keys),
                     'edge_csv_parity':comparable(csv_edges,edge_keys)==comparable(edges,edge_keys),
                     'dangling_count':len(dangling),'component_sizes':sorted(sizes,reverse=True),
                     'raw_id_labels':[n['id'] for n in nodes.values() if n['id']==n['label']],
                     'overrides':[e for e in edges if e['edge_type']=='OVERRIDES'],
                     'claim_id_count':sum(bool(e.get('claim_id') or e.get('edge_id')) for e in edges),
                     'passage_id_count':sum(bool(e.get('source_passage_id') or e.get('passage_id')) for e in edges),
                     'entity_role_count':sum(bool(n.get('entity_role')) for n in nodes.values()),
                     'baseline_keys':list(base) if base else None,
                     'baseline_counts':[len(base['nodes']),len(base['edges'])] if base else None},
            'inventories':resolved}


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output', type=Path);args=parser.parse_args()
    result=run()
    if args.output:
        target=args.output.resolve()
        if target.parent != Path(__file__).resolve().parent:
            parser.error('Output must be in this audit directory')
        target.write_text(json.dumps(result,indent=2,ensure_ascii=True)+'\n',encoding='utf-8')
    print(json.dumps({'graph':result['graph'], 'inventories':{k:{field:(len(value) if isinstance(value,list) else value)
          for field,value in v.items() if field!='rows'} for k,v in result['inventories'].items()}},indent=2))
