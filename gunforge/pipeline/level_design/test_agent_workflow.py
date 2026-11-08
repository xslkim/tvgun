import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from agent_workflow import propose,CompileError
from versions import publish
from build_gallery import source
class AgentWorkflowTests(unittest.TestCase):
 def test_scope_invariants_evidence_and_candidate(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);store=root/'store';entry=publish(copy.deepcopy(source),store);evidence=root/'frame.txt';evidence.write_text('test-only evidence')
   task={'package':source['id'],'base_revision':entry.parent.name,'evidence':[{'path':str(evidence),'sha256':hashlib.sha256(evidence.read_bytes()).hexdigest()}],'allowed_paths':['/events/next/trigger/at_ms'],'preserve':['/entities/protected_a']}
   patch={'base_revision':entry.parent.name,'changes':[{'path':'/events/next/trigger/at_ms','expected':2000,'value':4000}]}
   t=root/'task.json';p=root/'patch.json'
   def save():t.write_text(json.dumps(task));p.write_text(json.dumps(patch))
   save();result=propose(t,p,store);self.assertEqual(result['state'],'candidate_not_adopted');self.assertFalse((store/'adopted').exists())
   task['preserve']=['/events/next/trigger/at_ms'];save()
   with self.assertRaises(CompileError):propose(t,p,store)
   task['preserve']=[];task['allowed_paths']=['/entities/target_a'];save()
   with self.assertRaises(CompileError):propose(t,p,store)
   evidence.write_text('changed');save()
   with self.assertRaises(CompileError):propose(t,p,store)
if __name__=='__main__':unittest.main()
