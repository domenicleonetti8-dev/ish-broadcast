from __future__ import annotations
import ast, hashlib, json, sqlite3, tempfile
from pathlib import Path

SOURCE = Path(__file__).with_name('EIRA2_UNIVERSE_LIBRARY_FULL_REPLACEMENT_V1.py')

def payload():
    tree=ast.parse(SOURCE.read_text())
    for n in tree.body:
        if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='NEW' for t in n.targets):
            return ast.literal_eval(n.value)
    raise RuntimeError('NEW_missing')

def seed(**kw):
    x={'subject':'Earth','canonical_claim':'Earth is a planet in the Solar System.','domain':'earth','epistemic_class':'fact','temporal_scope':'current','geographic_or_cosmic_scope':'Earth','truth_state':'accepted','confidence':0.99,'version':1,'metadata':{}}
    x.update(kw); return x

def src(uri='https://example.test/a',h='a'*64): return {'source_uri':uri,'retrieved_at':'2026-09-07T00:00:00Z','source_hash':h,'publisher':'test'}

def run_round(ns):
    U=ns['UniverseLibrary']; Invalid=ns['InvalidSeedError']; UE=ns['UniverseLibraryError']; checks=[]
    def ck(name,fn):
        try: fn(); checks.append((name,True,''))
        except Exception as e: checks.append((name,False,f'{type(e).__name__}:{e}'))
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'u.db'; lib=U(p)
        r=lib.archive_seed(seed(),[src()]); sid=r.seed_id
        ck('01_schema_v1',lambda: (_ for _ in ()).throw(AssertionError()) if lib.schema_version()!=1 else None)
        ck('02_insert',lambda: (_ for _ in ()).throw(AssertionError()) if not r.inserted else None)
        ck('03_seed_id_sha',lambda: (_ for _ in ()).throw(AssertionError()) if not sid.startswith('seed_') or len(sid)!=69 else None)
        ck('04_retrieve',lambda: (_ for _ in ()).throw(AssertionError()) if lib.get_seed(sid)['canonical_claim']!=seed()['canonical_claim'] else None)
        r2=lib.archive_seed(seed(),[src()])
        ck('05_duplicate_idempotent',lambda: (_ for _ in ()).throw(AssertionError()) if r2.inserted else None)
        ck('06_one_seed_row',lambda: (_ for _ in ()).throw(AssertionError()) if lib.db.execute('select count(*) from seeds').fetchone()[0]!=1 else None)
        lib.archive_seed(seed(),[src('https://example.test/b','b'*64)])
        ck('07_provenance_merge',lambda: (_ for _ in ()).throw(AssertionError()) if len(lib.get_seed(sid)['sources'])!=2 else None)
        ck('08_case_space_identity',lambda: (_ for _ in ()).throw(AssertionError()) if ns['canonical_seed_id'](subject=' EARTH ',claim='earth  is a planet in the solar system.',temporal_scope='current',epistemic_class='fact')!=sid else None)
        def invalid_missing():
            q=seed(); q.pop('subject'); lib.archive_seed(q)
        ck('09_missing_rejected',lambda: expect(Invalid,invalid_missing))
        ck('10_bad_truth_rejected',lambda: expect(Invalid,lambda:lib.archive_seed(seed(truth_state='banana'))))
        ck('11_bad_class_rejected',lambda: expect(Invalid,lambda:lib.archive_seed(seed(epistemic_class='banana'))))
        ck('12_conf_low_rejected',lambda: expect(Invalid,lambda:lib.archive_seed(seed(confidence=-.1))))
        ck('13_conf_high_rejected',lambda: expect(Invalid,lambda:lib.archive_seed(seed(confidence=1.1))))
        ck('14_version_rejected',lambda: expect(Invalid,lambda:lib.archive_seed(seed(version=0))))
        ck('15_source_contract',lambda: expect(Invalid,lambda:lib.archive_seed(seed(),[{'source_uri':'x'}])))
        moon=lib.archive_seed(seed(subject='Moon',canonical_claim='The Moon orbits Earth.',domain='solar',geographic_or_cosmic_scope='Moon'),[src('https://example.test/m','c'*64)]).seed_id
        ck('16_second_unique_seed',lambda: (_ for _ in ()).throw(AssertionError()) if lib.db.execute('select count(*) from seeds').fetchone()[0]!=2 else None)
        ck('17_edge_add',lambda: (_ for _ in ()).throw(AssertionError()) if not lib.add_edge(moon,'orbits',sid) else None)
        ck('18_edge_dedup',lambda: (_ for _ in ()).throw(AssertionError()) if lib.add_edge(moon,'orbits',sid) else None)
        ck('19_self_edge_rejected',lambda: expect(UE,lambda:lib.add_edge(sid,'related_to',sid)))
        ck('20_empty_relation_rejected',lambda: expect(UE,lambda:lib.add_edge(moon,'',sid)))
        newer=lib.archive_seed(seed(temporal_scope='future_revision',canonical_claim='Earth remains classified as a planet.',version=2),[src('https://example.test/n','d'*64)]).seed_id
        lib.supersede(sid,newer,'test')
        ck('21_supersession_marks_old',lambda: (_ for _ in ()).throw(AssertionError()) if lib.get_seed(sid)['truth_state']!='superseded' else None)
        ck('22_supersession_link',lambda: (_ for _ in ()).throw(AssertionError()) if lib.db.execute('select new_seed_id from supersession where old_seed_id=?',(sid,)).fetchone()[0]!=newer else None)
        ck('23_self_supersession_rejected',lambda: expect(UE,lambda:lib.supersede(newer,newer)))
        ck('24_indexes_exist',lambda: (_ for _ in ()).throw(AssertionError()) if len(lib.db.execute("select name from sqlite_master where type='index' and name like 'idx_%'").fetchall())<6 else None)
        ck('25_wal_enabled',lambda: (_ for _ in ()).throw(AssertionError()) if lib.db.execute('pragma journal_mode').fetchone()[0].lower()!='wal' else None)
        lib.close()
    return checks

def expect(exc,fn):
    try: fn()
    except exc: return
    raise AssertionError('expected_exception_not_raised')

def main():
    code=payload(); compile(code,'universe_library.py','exec'); ns={}; exec(compile(code,'universe_library.py','exec'),ns)
    rounds=[run_round(ns),run_round(ns)]
    passed=sum(ok for rr in rounds for _,ok,_ in rr); failures=[{'round':i+1,'test':n,'error':e} for i,rr in enumerate(rounds) for n,ok,e in rr if not ok]
    out={'schema':'eira2_universe_library_25x2_v1','source_sha256':hashlib.sha256(code.encode()).hexdigest(),'rounds':2,'distinct_tests':25,'total':50,'passed':passed,'failed':len(failures),'status':'PASS' if passed==50 else 'FAIL','failures':failures}
    print(json.dumps(out,indent=2,sort_keys=True)); raise SystemExit(0 if passed==50 else 1)
if __name__=='__main__': main()
