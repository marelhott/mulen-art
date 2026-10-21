import hashlib, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from app_runtime import archives, core, server

class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.items=[]
        for n in range(3):
            p=self.root/f'{n}.png';Image.new('RGB',(512,768),(n*80,90,50)).save(p)
            self.items.append({'id':str(n),'filename':f'work{n}.png','path':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
        self.manifest={'archives':[{'id':'hofmann','name':'Julius Hofmann','count':3,'items':self.items}]}
        (self.root/'manifest.json').write_text(json.dumps(self.manifest))
        self.root_patch=patch.object(archives,'archive_root',return_value=self.root);self.root_patch.start()
    def tearDown(self):
        self.root_patch.stop();self.tmp.cleanup()
    def test_seed_selection_matches_between_models_and_covers_cycle(self):
        selected=[archives.reference_for('hofmann',seed)[1]['id'] for seed in range(3)]
        self.assertEqual(len(set(selected)),3)
        self.assertEqual(archives.reference_for('hofmann',10)[1],archives.reference_for('hofmann',10)[1])
        with self.assertRaises(ValueError):archives.reference_for('missing',1)
        selected_path=archives.reference_for('hofmann',0)[2];selected_path.write_bytes(b'corrupted')
        with self.assertRaisesRegex(ValueError,'integrity'):archives.reference_for('hofmann',0)
    def test_cross_artist_repaint_keeps_provenance_and_empty_prompt(self):
        spec=core.parse_input({'generation_type':'atelier','atelier_mode':'archive','atelier_archive':'hofmann',
            'model_id':'tuymans_modal_2400','seed':5,'width':1024,'height':1024,'denoise':0.55,'cfg':0.5,'steps':28})
        seen=[];emitted=[]
        def generate(payload,progress,callback,extra_meta=None):
            seen.append(payload)
            image=core.decode_image(payload['image_base64'])
            callback(core.encode_image(image),{'model_id':payload['model_id'],'seed':payload['seed'],'denoise':payload['denoise']})
            return {'meta':{}}
        with patch.object(core,'generate',side_effect=generate),patch.object(server,'OUTPUTS_DIR',self.root):
            result=archives.generate_reference(spec,None,lambda image,meta:emitted.append(meta))
        self.assertEqual(seen[0]['model_id'],'tuymans_modal_2400')
        self.assertEqual(seen[0]['generation_type'],'img2img')
        self.assertEqual(seen[0]['prompt'],'')
        self.assertEqual(seen[0]['denoise'],0.55)
        self.assertEqual(emitted[0]['atelier_archive'],'hofmann')
        self.assertEqual(emitted[0]['generation_type'],'atelier')
        self.assertEqual(emitted[0]['subject_origin'],'reference-archive')
        self.assertEqual((result['images'][0]['width'],result['images'][0]['height']),(512,768))
        self.assertEqual(len(list(self.root.glob('source_archive_*.png'))),1)
    def test_traversal_is_rejected(self):
        for item in self.manifest['archives'][0]['items']:item['path']='../outside.png'
        (self.root/'manifest.json').write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError,'unavailable'):archives.reference_for('hofmann',0)
