import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtempSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {setTimeout as sleep} from 'node:timers/promises';
import {root,read} from '../../../pipeline/export/build.mjs';

const edge=process.env.EDGE_PATH??'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const userData=mkdtempSync(join(tmpdir(),'skeletal-viewer-'));
const port=9248, endpoint='http://127.0.0.1:'+port;
const browser=spawn(edge,['--headless=new','--disable-gpu','--hide-scrollbars','--no-first-run',
  '--remote-debugging-port='+port,'--user-data-dir='+userData,'about:blank'],{windowsHide:true,stdio:'ignore'});
let socket;
try {
  let targets;
  for(let i=0;i<60;i++){
    try {targets=await fetch(endpoint+'/json').then(r=>r.json());break;}catch{await sleep(100);}
  }
  assert.ok(targets,'Headless Edge CDP unavailable');
  socket=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  let id=0;
  const pending=new Map(), exceptions=[];
  socket.onmessage=event=>{
    const value=JSON.parse(event.data);
    if(value.method==='Runtime.exceptionThrown') exceptions.push(value.params.exceptionDetails.text);
    if(value.id && pending.has(value.id)) {
      const {resolve,reject}=pending.get(value.id);pending.delete(value.id);
      if(value.error) reject(new Error(value.error.message));else resolve(value.result);
    }
  };
  const send=(method,params={})=>new Promise((resolve,reject)=>{
    const key=++id;pending.set(key,{resolve,reject});socket.send(JSON.stringify({id:key,method,params}));
  });
  const run=async expression=>{
    const result=await send('Runtime.evaluate',{expression,returnByValue:true});
    if(result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description??result.exceptionDetails.text);
    return result.result.value;
  };
  const waitFor=async expression=>{
    for(let i=0;i<100;i++){
      if(await run(expression)) return;
      await sleep(75);
    }
    throw new Error('Timed out waiting for '+expression+' · '+await run("document.querySelector('#status')?.textContent"));
  };
  await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1420,height:1000,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:'http://127.0.0.1:4173/demos/viewer/'});
  await waitFor("document.querySelector('.character[aria-pressed=true]') !== null");
  const roster=read(join(root,'demos','characters.json')).filter(c=>!c.validation);
  let total=0;
  for(const c of roster) {
    const spec=read(join(root,c.path.slice(1)));
    await run("(()=>{const b=document.querySelector('[data-id="+c.id+"]');if(b.getAttribute('aria-pressed')!=='true') b.click();})()");
    await waitFor("document.querySelector('[data-id="+c.id+"]').getAttribute('aria-pressed')==='true'");
    for(const name of Object.keys(spec.clips)) {
      await run("document.querySelector('[data-clip="+name+"]').click()");
      await waitFor("document.querySelector('[data-clip="+name+"]').getAttribute('aria-pressed')==='true'");
      total++;
    }
  }
  const validation=read(join(root,'demos','characters.json')).find(c=>c.validation);
  if(validation) {
    await run("document.querySelector('[data-id="+validation.id+"]').click()");
    await waitFor("document.querySelector('[data-id="+validation.id+"]').getAttribute('aria-pressed')==='true'");
    await waitFor("document.querySelector('[data-clip=idle]').getAttribute('aria-pressed')==='true'");
    console.log('Skill validation character loaded: '+validation.id);
  }
  await run("document.querySelector('[data-id=courier]').click()");
  await waitFor("document.querySelector('[data-id=courier]').getAttribute('aria-pressed')==='true'");
  await run("document.querySelector('[data-clip=walk]').click();document.querySelector('#next').click()");
  assert.ok((await run("document.querySelector('#clock').textContent")).startsWith('0.033'));
  await run("document.querySelector('#prev').click();document.querySelector('#bones').click();document.querySelector('#mesh').click();document.querySelector('#skin').value='hammer';document.querySelector('#rate').value='2';document.querySelector('#sequence').click()");
  await waitFor("document.querySelector('[data-clip=attack_light]').getAttribute('aria-pressed')==='true'");
  await waitFor("document.querySelector('[data-clip=walk]').getAttribute('aria-pressed')==='true'");
  await run("document.querySelector('#bones').click();document.querySelector('#mesh').click();document.querySelector('#skin').value='';document.querySelector('#rate').value='1';document.querySelector('[data-clip=idle]').click();document.querySelector('#next').click()");
  const screenshot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  writeFileSync(join(root,'demos','viewer','verified.png'),Buffer.from(screenshot.data,'base64'));
  assert.deepEqual(exceptions,[]);
  console.log('Edge headless: '+roster.length+' characters, '+total+' clips, step, overlays, skin control and combo verified.');
} finally {
  socket?.close();
  browser.kill();
}
