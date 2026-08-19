from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
from omnivenom_mesh_ai.runtime import Omnivenom


class OmnivenomTests(unittest.TestCase):
    def make_live(self,td):
        r=Path(td);(r/'extensions/unified_brain_ai').mkdir(parents=True);(r/'extensions/local_brain').mkdir(parents=True);(r/'data').mkdir()
        (r/'extensions/unified_brain_ai/__init__.py').write_text('')
        (r/'extensions/local_brain/__init__.py').write_text('')
        (r/'extensions/local_brain/router.py').write_text('def chat(x):\n return "old:"+x\n')
        return r

    def test_crawl_find_unknown_resolve_and_brain_roles(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.make_live(td);ext=r/'extensions/tool';ext.mkdir();(ext/'__init__.py').write_text('')
            (ext/'manifest.json').write_text(json.dumps({'name':'tool','entrypoint':'extensions.tool.plugin','capabilities':['special_findable']}))
            (ext/'plugin.py').write_text('from extensions.missing_piece import helper\ndef ask(x): return x\n')
            m=Omnivenom(r,r/'data/mesh.db');out=m.refresh()
            self.assertTrue(m.find('special_findable'))
            self.assertTrue(m.find('missing_piece'))
            self.assertIn('unified_brain_ai',out['brains']);self.assertIn('local_brain',out['brains'])
            # recovered module later appears and is connected
            (r/'extensions/missing_piece.py').write_text('def helper(): return 1\n')
            out2=m.refresh();self.assertGreaterEqual(out2['morph']['resolved_unknowns'],1)

    def test_crawl_never_imports_discovered_python(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.make_live(td);marker=r/'EXECUTED';(r/'extensions/evil.py').write_text(f"open({str(marker)!r},'w').write('bad')\n")
            Omnivenom(r,r/'data/mesh.db').refresh();self.assertFalse(marker.exists())

    def test_symlink_not_followed(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outside:
            r=self.make_live(td);secret=Path(outside)/'secret.py';secret.write_text('x=1')
            try:(r/'extensions/link.py').symlink_to(secret)
            except OSError:self.skipTest('symlink unsupported')
            m=Omnivenom(r,r/'data/mesh.db');m.refresh();rows=m.find('link.py');self.assertTrue(rows);self.assertEqual(rows[0]['kind'],'symlink')

    def test_stable_node_id_is_directly_findable(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.make_live(td);m=Omnivenom(r,r/'data/mesh.db');m.refresh();row=m.find('router.py')[0];self.assertEqual(m.find(row['node_id'])[0]['node_id'],row['node_id'])

    def test_one_output_is_dominant(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.make_live(td);m=Omnivenom(r,r/'data/mesh.db');m.refresh()
            seen={}
            def old(payload):seen['old']=payload;return 'legacy advice'
            def new(payload):seen['new']=payload;return 'EIRA FINAL'
            b=m.bind(new,old);out=b.respond('hello')
            self.assertEqual(out,'EIRA FINAL');self.assertEqual(seen['new']['legacy_advisory'],'legacy advice')
            self.assertFalse(seen['old']['outward']);self.assertEqual(seen['new']['authority']['outward_outputs'],1)

    def test_moved_artifact_reconnects_by_hash(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.make_live(td);src=r/'extensions/lost.py';src.write_text('def relic(): return 7\n')
            m=Omnivenom(r,r/'data/mesh.db');m.refresh();old=m.find('extensions/lost.py')[0]['node_id']
            dst=r/'extensions/recovered.py';src.rename(dst)
            out=m.refresh();self.assertGreaterEqual(out['morph']['recovered_locations'],1)
            with m.store._db() as db:
                rows=[dict(x) for x in db.execute("SELECT * FROM lineage WHERE old_node_id=?",(old,)).fetchall()]
            self.assertTrue(any(x['relation']=='moved_to' for x in rows))

    def test_removed_artifact_remains_registered_missing(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.make_live(td);p=r/'extensions/old_artifact.py';p.write_text('x=1\n')
            m=Omnivenom(r,r/'data/mesh.db');m.refresh();nid=m.find('old_artifact.py')[0]['node_id'];p.unlink();m.refresh()
            row=m.find(nid)[0];self.assertEqual(row['state'],'missing')

    def test_every_registered_node_is_findable_by_id_and_topology_connected(self):
        with tempfile.TemporaryDirectory() as td:
            r=self.make_live(td);(r/'extensions/x.py').write_text('import json\ndef f(): return json.dumps({})\n')
            m=Omnivenom(r,r/'data/mesh.db');m.refresh();status=m.status();self.assertEqual(status['topology']['unreachable'],0)
            for row in m.store.nodes():
                self.assertEqual(m.find(row['node_id'])[0]['node_id'],row['node_id'])

if __name__=='__main__':unittest.main()
