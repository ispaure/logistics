"""Native image quads, recovery, mixed stacking and protected PDF contracts."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
from io import BytesIO
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from pypdf import PdfReader
from features.notebooks.notebook import Notebook
from features.notebooks.editor import Editor
from features.notebooks.images import ImageResources, ImageItem, image_payloads
from features.notebooks.recovery import Repository


from Python.tests.notebooks.image_fixtures import png_source, paste_action, locked_book

class NotebookImageTests(unittest.TestCase):
    def test_real_pen_input_paints_before_incremental_stroke_acknowledgement(self):
        import json
        from pathlib import Path
        import shutil
        import subprocess
        if not shutil.which('node'):
            self.skipTest('Node is required for the production input/acknowledgement contract')
        assets = Path(__file__).resolve().parents[2] / 'features/notebooks/assets'
        driver = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const controls=new Map(),events=[],listeners=[];
const node=()=>({value:'',style:{},classList:{add(){},remove(){},toggle(){}},
  setAttribute(){},append(){},set innerHTML(value){}});
const control=id=>{if(!controls.has(id))controls.set(id,node());return controls.get(id)};
const s={console,events,$:control,document:{body:node(),createElement:node},
  canvas:{style:{},addEventListener:(kind,handler)=>listeners.push({kind,handler}),getBoundingClientRect:()=>({left:0,top:0,width:1404,height:1872})},
  state:{width:1404,height:1872,index:0,count:1,strokes:[],native_pen:false},
  mode:'ink',active:null,last:null,start:null,points:[],pan:null,selected:new Set(),
  touchContacts:new Map(),penContactActive:false,continuousInk:true,frameBatchedInk:false,
  viewportResizePending:false,deferredUpdate:null,pendingInk:null,queue:[],busy:false,
  bridge:'notebook://contract/',seq:0,pageSwipe:false,
  chosenInk:()=>({tool:17,color:0,width:3,layer:'L'}),
  brushFor:()=>({family:'fineliner'}),brushOptions(){},
  notePenContact(value){s.penContactActive=value},penTouchBlocked:()=>false,
  cancelTouchZoom(){},flushPreview(){if(s.points.length)events.push('paint')},
  cancelPreview(){},draw(){events.push('draw')},render(){events.push('render')},
  strokeExpandsPaper:()=>false};
s.performance={now:()=>1000};s.window=s;vm.createContext(s);
vm.runInContext(fs.readFileSync(process.argv[1]+'/input.js','utf8'),s);
vm.runInContext(fs.readFileSync(process.argv[1]+'/queue.js','utf8')
  .replaceAll('__MAX_COMMAND__','100000').replaceAll('__SEND_COMMAND__',"events.push('send')"),s);
const stroke={id:'S',layer:'L',tool:17,color:0,points:[[670,936,.5,5.25],[730,936,.5,5.25]]};
// A bare command cannot stand in for visible input: interior ack does not paint.
s.send({op:'stroke',tool:17,color:0,width:3,points:[[670,936,.5],[730,936,.5]]});
s.notebookStrokeUpdate(stroke,'Saved');
assert.deepEqual(events,['send']);assert.equal(s.state.strokes.length,1);
s.state.strokes=[];events.length=0;
const event=x=>({pointerId:7,pointerType:'pen',nativePen:true,clientX:x,clientY:936,
  pressure:.5,preventDefault(){}});
s.canvas.onpointerdown(event(670));s.canvas.onpointermove(event(730));s.canvas.onpointerup(event(730));
assert.equal(s.queue.length,1);assert.equal(s.queue[0].op,'stroke');
assert.equal(s.queue[0].tool,17);assert.equal(s.queue[0].color,0);assert.equal(s.queue[0].layer,'L');
assert.ok(events.indexOf('paint')>=0&&events.indexOf('paint')<events.indexOf('send'),events);
const painted=events.filter(value=>value==='paint').length;
s.notebookStrokeUpdate(stroke,'Saved');
assert.equal(s.state.strokes.length,1);assert.equal(s.state.strokes[0].id,'S');
assert.equal(events.filter(value=>value==='paint').length,painted);
assert.ok(!events.includes('draw')&&!events.includes('render'),events);
assert.equal(s.queue.length,0);assert.equal(s.busy,false);
assert.equal(s.logisticsInputTrace().counts['accepted-down:pen'],1);
assert.equal(s.logisticsInputTrace().counts['stroke-ack-applied:host'],2);
assert.ok(listeners.every(row=>typeof row.handler==='function'));
console.log(JSON.stringify({passed:true,bare_command_does_not_paint:true,pen_paints_before_ack:true}));
"""
        result = subprocess.run(['node', '-e', driver, str(assets)], capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)['passed'])

    def test_native_png_roundtrip_transforms_unchanged_ink_and_resources(self):
        book = Notebook.new(); editor = Editor(book)
        editor.apply(dict(op='stroke', points=[[40,50,.5],[90,80,.9]]))
        editor.apply(paste_action())
        saved = Notebook.read(book.to_bytes()); ink = saved.page(0)
        self.assertFalse(ink.warning)
        self.assertEqual(len(ink.images), 1)
        self.assertEqual(len(ink.strokes), 1)
        self.assertTrue(any(isinstance(b, ImageResources) for b in ink._blocks))
        native = ink.to_bytes()
        self.assertEqual(native, ink.raw)
        baseline = dict(saved.members)
        stroke_frames = [raw for raw,b in zip(ink._frames,ink._blocks) if type(b).__name__ == 'SceneLineItemBlock']
        picture = ink.images[0]
        corners = [[x+30,y+60] for x,y in picture.corners]
        editing = Editor(saved)
        editing.apply(dict(op='image-transform', id=picture.id, corners=corners))
        reopened = Notebook.read(saved.to_bytes())
        self.assertEqual(reopened.page(0).images[0].corners, corners)
        self.assertEqual([raw for raw,b in zip(reopened.page(0)._frames,reopened.page(0)._blocks)
                          if type(b).__name__ == 'SceneLineItemBlock'], stroke_frames)
        self.assertEqual({k:v for k,v in reopened.members.items() if k.endswith('.png')},
                         {k:v for k,v in baseline.items() if k.endswith('.png')})
        self.assertEqual(image_payloads(reopened,0)[0]['src'], png_source())
        editing.apply(dict(op='undo'))
        self.assertEqual(saved.page(0).to_bytes(), native)
        editing.apply(dict(op='redo'))
        self.assertEqual(saved.page(0).images[0].corners, corners)

    def test_recovery_repeated_paste_cross_page_copy_and_undo(self):
        with TemporaryDirectory() as directory:
            repository = Repository(directory)
            book = Notebook.new(); key = repository.create(book)
            editor = Editor(book, lambda value: repository.save(key,value))
            editor.apply(paste_action()); editor.apply(paste_action())
            self.assertEqual(len(book.page(0).images),2)
            self.assertNotEqual(book.page(0).images[0].resource,book.page(0).images[1].resource)
            editor.apply(dict(op='add-page')); editor.apply(paste_action())
            editor.apply(dict(op='duplicate-page'))
            recovered = repository.open(key)
            self.assertEqual([len(recovered.page(i).images) for i in range(3)],[2,1,1])
            self.assertEqual(image_payloads(recovered,2)[0]['src'],png_source())
            editor.apply(dict(op='undo'));editor.apply(dict(op='undo'))
            self.assertEqual(len(book.page(1).images),0)
            editor.apply(dict(op='redo'));editor.apply(dict(op='redo'))
            target=Notebook.new();target.copy_page(book,0)
            self.assertEqual(len(Notebook.read(target.to_bytes()).page(1).images),2)
            self.assertEqual(image_payloads(target,1)[0]['src'],png_source())

    def test_arrange_images_among_strokes_then_draw_above(self):
        with TemporaryDirectory() as directory:
            repository=Repository(directory);book=Notebook.new();key=repository.create(book)
            editor=Editor(book,lambda value:repository.save(key,value))
            editor.apply(dict(op='stroke', points=[[20,20,.5],[40,40,.5]]))
            editor.apply(paste_action())
            editor.apply(dict(op='stroke', points=[[60,60,.5],[80,80,.5]]))
            ink=book.page(0); a,b=ink.strokes; picture=ink.images[0]
            self.assertEqual(ink.order,[a.id,picture.id,b.id])
            for direction, expected in [('back',[picture.id,a.id,b.id]),('forward',[a.id,picture.id,b.id]),('front',[a.id,b.id,picture.id]),('backward',[a.id,picture.id,b.id])]:
                editor.apply(dict(op='arrange-image',id=picture.id,direction=direction))
                self.assertEqual(book.page(0).order,expected)
                self.assertEqual(Notebook.read(book.to_bytes()).page(0).order,expected)
            editor.apply(dict(op='stroke', points=[[90,90,.5]]))
            self.assertEqual(book.page(0).order[-1],book.page(0).strokes[-1].id)
            editor.apply(dict(op='undo'))
            self.assertEqual(book.page(0).order,[a.id,picture.id,b.id])

    def test_failed_checkpoint_rolls_back_assets_geometry_and_order(self):
        book=Notebook.new();editor=Editor(book)
        before=book.to_bytes()
        editor.checkpoint=lambda value:(_ for _ in ()).throw(OSError('disk full'))
        with self.assertRaises(OSError):editor.apply(paste_action())
        self.assertFalse(book.page(0).images)
        self.assertFalse(any(k.endswith('.png') for k in book.members))
        self.assertEqual(Notebook.read(before).page(0).to_bytes(),book.page(0).to_bytes())

    def test_reject_invalid_images_geometry_and_hidden_layer(self):
        book=Notebook.new();editor=Editor(book)
        for fields in [dict(src='data:image/png;base64,AAAA'), dict(corners=[[0,0]]),
                       dict(corners=[[0,0],[10,0],[11,10],[0,10]]),dict(layer='missing')]:
            with self.subTest(fields=fields),self.assertRaises((ValueError, OSError)):
                editor.apply({**paste_action(),**fields})
        self.assertFalse(book.page(0).images)
        self.assertFalse(any(k.endswith('.png') for k in book.members))

    def test_delete_retains_asset_but_tombstones_quad(self):
        book=Notebook.new();editor=Editor(book);editor.apply(paste_action())
        loaded=Notebook.read(book.to_bytes());editor=Editor(loaded)
        editor.apply(dict(op='delete-image',id=loaded.page(0).images[0].id))
        result=Notebook.read(loaded.to_bytes());self.assertFalse(result.page(0).images)
        self.assertTrue(any(isinstance(b,ImageItem) and b.item.deleted_length for b in result.page(0)._blocks))
        self.assertTrue(any(k.endswith('.png') for k in result.members))
        editor.apply(dict(op='undo'));self.assertEqual(len(loaded.page(0).images),1)

    def test_password_unlock_retry_memory_only_and_preserved_pdf(self):
        for algorithm in ['RC4-128','AES-128','AES-256']:
            with self.subTest(algorithm=algorithm):
                book=locked_book(algorithm=algorithm);original=book.members[book.id+'.pdf'];editor=Editor(book)
                with patch.object(editor,'background',return_value=None):
                    self.assertTrue(editor.state()['password_required'])
                    with self.assertRaisesRegex(ValueError,'Incorrect'):editor.apply(dict(op='unlock-pdf',password='wrong'))
                    self.assertTrue(editor.state()['password_required'])
                    editor.apply(dict(op='unlock-pdf',password='secret'))
                    self.assertFalse(editor.state()['password_required'])
                    self.assertEqual(editor.undo,[])
                    self.assertFalse(PdfReader(BytesIO(editor.pdf_data())).is_encrypted)
                    editor.apply(paste_action())
                    saved=Notebook.read(book.to_bytes())
                    self.assertEqual(saved.members[saved.id+'.pdf'],original)
                    self.assertTrue(PdfReader(BytesIO(original)).is_encrypted)
                    self.assertIsNone(Editor(saved).pdf_data())
                    self.assertEqual(len(saved.page(0).images),1)

    def test_system_aes_matches_nist_vectors(self):
        from features.notebooks.pdf_crypto import aes
        key=bytes.fromhex('2b7e151628aed2a6abf7158809cf4f3c')
        plain=bytes.fromhex('6bc1bee22e409f96e93d7e117393172a')
        for iv, expected in [(None,'3ad77bb40d7a3660a89ecaf32466ef97'),
                             (bytes(range(16)),'7649abac8119b246cee98e9b12e9197d')]:
            with self.subTest(iv=iv):
                encrypted=aes(key,plain,iv=iv)
                self.assertEqual(encrypted.hex(),expected)
                self.assertEqual(aes(key,encrypted,iv=iv,decrypt=True),plain)

    def test_erasing_splits_ink_at_its_image_stacking_position(self):
        with TemporaryDirectory() as directory:
            repository=Repository(directory);book=Notebook.new();key=repository.create(book)
            editor=Editor(book,lambda value:repository.save(key,value))
            editor.apply(dict(op='stroke',points=[[100,200,.5],[500,200,.5]],tool=17,width=1))
            editor.apply(paste_action())
            editor.apply(dict(op='erase',points=[[300,180,.5],[300,220,.5]],radius=8))
            ink=book.page(0)
            self.assertEqual(len(ink.strokes),2)
            self.assertEqual(ink.order,[s.id for s in ink.strokes]+[ink.images[0].id])
            self.assertEqual(Notebook.read(book.to_bytes()).page(0).order,ink.order)

    def test_unlocked_pdf_survives_structural_recovery_publication(self):
        with TemporaryDirectory() as directory:
            repository=Repository(directory);book=locked_book(password='image-qa-password')
            key=repository.create(book)
            editor=Editor(book,lambda value:repository.save(key,value))
            editor.apply(dict(op='unlock-pdf',password='image-qa-password'))
            original=book.members[book.id+'.pdf']
            decrypted=editor.pdf_data()
            editor.apply(paste_action())
            self.assertEqual(book.members[book.id+'.pdf'],original)
            self.assertIsNot(book.members[book.id+'.pdf'],original)
            self.assertEqual(editor.pdf_data(),decrypted,'Identical encrypted bytes must retain the session unlock')
            editor.apply(paste_action())
            self.assertEqual(len(book.page(0).images),2)
            self.assertEqual(editor.pdf_data(),decrypted)
            self.assertIsNone(Editor(repository.open(key)).pdf_data(),'A new editor must still ask for the password')

    def test_different_embedded_pdf_bytes_invalidate_session_unlock(self):
        book=locked_book(password='first-password');editor=Editor(book)
        editor.apply(dict(op='unlock-pdf',password='first-password'))
        self.assertIsNotNone(editor.pdf_data())
        replacement=locked_book(password='second-password')
        book.members[book.id+'.pdf']=replacement.members[replacement.id+'.pdf']
        self.assertIsNone(editor.pdf_data())
        with self.assertRaisesRegex(ValueError,'Incorrect'):
            editor.apply(dict(op='unlock-pdf',password='first-password'))
        editor.apply(dict(op='unlock-pdf',password='second-password'))
        self.assertIsNotNone(editor.pdf_data())

    def test_page_identity_is_stable_when_pages_move(self):
        book=Notebook.new();editor=Editor(book)
        first=editor.state()['page_id']
        editor.apply(dict(op='add-page'))
        second=editor.state()['page_id']
        self.assertNotEqual(first,second)
        editor.apply(dict(op='move-page',index=0))
        self.assertEqual(editor.state()['page_id'],second)
        self.assertEqual(editor.index,0)

    def test_empty_password_pdf_opens_without_prompt(self):
        editor=Editor(locked_book(password=''))
        self.assertIsNotNone(editor.pdf_data())


if __name__ == '__main__':
    unittest.main()
