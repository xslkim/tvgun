// Use the installed OCR engine; no text guesses or fabricated scores.
const fs=require('node:fs');
const path=require('node:path');
async function main(){
  const root=process.env.ART_NODE_MODULES||'C:/Users/xsl/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
  const {createWorker}=require(path.join(root,'tesseract.js'));
  const cache='D:/gunforge_cache/ocr';fs.mkdirSync(cache,{recursive:true});
  const worker=await createWorker('eng+chi_sim',1,{cachePath:cache});
  try{const {data}=await worker.recognize(process.argv[2],{}, {blocks:true});const words=(data.blocks||[]).flatMap(b=>b.paragraphs.flatMap(p=>p.lines.flatMap(l=>l.words.map(w=>({text:w.text,confidence:w.confidence,bbox:w.bbox})))));process.stdout.write(JSON.stringify({text:data.text,confidence:data.confidence,words,engine:'tesseract.js-7.0.0-eng+chi_sim'}));}
  finally{await worker.terminate();}
}
main().catch(e=>{process.stderr.write(String(e));process.exitCode=1;});
