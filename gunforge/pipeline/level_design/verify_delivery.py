"""Rebuild in an independent source directory with a new venv and empty build cache."""
import argparse,hashlib,json,os,shutil,subprocess,time
from pathlib import Path
from paths import ROOT,CACHE,GODOT
from freeze_baseline import dump,sha

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--godot',type=Path,default=GODOT);args=parser.parse_args()
 out=CACHE/'runs'/('delivery-'+str(time.time_ns()));workspace=out/'workspace';workspace.mkdir(parents=True)
 folders=['gunforge/framework','gunforge/games/g01/scripts','gunforge/games/g01/levels','gunforge/games/g01/bible','gunforge/games/g01/assets/stations/g01_st_l1_01_alley','gunforge/level_design','gunforge/pipeline/level_design']
 files=['gunforge/pipeline/build_0b.py','gunforge/start_level_player.ps1','gunforge/start_level_review.ps1','play_level_prototype.cmd','review_levels.cmd','play_combat_candidate.cmd','review_combat_candidate.cmd']
 for folder in folders:
  for source in (ROOT/folder).rglob('*'):
   relative=source.relative_to(ROOT)
   if not source.is_file() or any(part in ['.godot','runtime','__pycache__','generated'] for part in relative.parts):continue
   destination=workspace/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
 for name in files:
  destination=workspace/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,destination)
 manifest={p.relative_to(workspace).as_posix():sha(p) for p in workspace.rglob('*') if p.is_file()}
 dump(out/'source-manifest.json',manifest)
 env=os.environ.copy();env['GODOT_BIN']=str(args.godot);env['GUNFORGE_LEVEL_CACHE']=str(out/'empty-build-cache');checks=[]
 def run(name,command,timeout=120):
  result=subprocess.run([str(x) for x in command],cwd=workspace,env=env,capture_output=True,timeout=timeout)
  log=result.stdout+result.stderr;(out/(name+'.log')).write_bytes(log)
  ok=result.returncode==0 and not any(x in log for x in [b'SCRIPT ERROR:',b'ObjectDB instances leaked',b'resources still in use'])
  checks.append({'name':name,'passed':ok,'log':str(out/(name+'.log'))})
  if not ok:raise RuntimeError(name+': '+log.decode(errors='replace')[-2000:])
  return log
 run('new-venv',['uv','venv',workspace/'.venv','--python','3.12.10'])
 python=workspace/'.venv/Scripts/python.exe'
 run('locked-dependencies',['uv','pip','install','--python',python,'-r','gunforge/pipeline/level_design/requirements.lock'])
 run('assets',[python,'gunforge/pipeline/build_0b.py'])
 run('godot-import',[args.godot,'--headless','--editor','--import','--quit','--path','gunforge/framework'])
 for name in ['gallery','paper','protection','assault']:
  run('build-'+name,[python,'gunforge/pipeline/level_design/build_'+name+'.py'])
  index=json.loads((workspace/'gunforge/level_design/reviews'/(name+'_build.json')).read_bytes())
  original=json.loads((ROOT/'gunforge/level_design/reviews'/(name+'_build.json')).read_bytes())
  if index['build_id']!=original['build_id']:raise RuntimeError('Independent build differs: '+name)
  run('bot-'+name,[args.godot,'--headless','--path','gunforge/framework','--script','res://tests/functional_bot.gd','--','--build='+index['compiled'],'--assets='+str(workspace),'--report='+str(out/(name+'-bot.json'))])
 index=json.loads((workspace/'gunforge/level_design/reviews/assault_build.json').read_bytes())
 run('reviewer',[args.godot,'--path','gunforge/framework','--script','res://tools/level_review.gd','--','--build='+index['compiled'],'--assets='+str(workspace),'--capture='+str(out/'independent-review.png'),'--capture-tick=260','--quit-after-capture'])
 run('player',[args.godot,'--path','gunforge/framework','--script','res://tools/level_player.gd','--','--build='+index['compiled'],'--assets='+str(workspace),'--quit-after=1','--isolated-settings'])
 run('candidate-doubleclick-launcher',['cmd.exe','/c','play_combat_candidate.cmd','-QuitAfter','0.3'])
 # Adoption fixture exists exclusively in the independent test workspace, never the live project.
 from versions import patch,adopt
 from checks import check
 from compiler import read
 store=workspace/'gunforge/level_design';gallery=read(store/'reviews/gallery_build.json')
 patched=patch('gallery.intro',gallery['source_revision'],{'base_revision':gallery['source_revision'],'changes':[{'path':'/events/next/trigger/at_ms','expected':2000,'value':2400}]},store)
 warnings=[warning['code'] for warning in check(patched)['warnings']]
 adopted=adopt('gallery.intro',patched.parent.name,None,'ISOLATED AUTOMATED TEST FIXTURE, not real user acceptance','user',store,out/'empty-build-cache',acknowledged_warnings=warnings)
 launch_log=run('adopted-source-launcher',['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File','gunforge/start_level_player.ps1','-Package','gallery.intro','-QuitAfter','0.3'])
 if adopted['build_id'].encode() not in launch_log:raise RuntimeError('Launcher failed to select isolated adopted source')
 result={'passed':True,'workspace':str(workspace),'run':str(out),'source_manifest':{'path':str(out/'source-manifest.json'),'sha256':sha(out/'source-manifest.json')},'checks':checks,'build_identity':'all four packages identical to original workspace','adoption_fixture':'isolated copied workspace only; live project adoption not performed','scope':'independent directory, new Python 3.12.10 venv, pinned dependencies, copied approved assets, empty build cache, actual GPU reviewer/player, candidate and adopted launch chains; no hardware claim'}
 dump(out/'index.json',result);dump(ROOT/'gunforge/level_design/reviews/delivery_acceptance.json',{'passed':True,'index':str(out/'index.json'),'sha256':sha(out/'index.json'),'checks':len(checks)})
 print(json.dumps({'passed':True,'run':str(out),'checks':len(checks)}))
if __name__=='__main__':main()
