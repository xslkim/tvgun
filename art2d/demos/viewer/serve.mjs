import {createReadStream,statSync} from 'node:fs';
import {createServer} from 'node:http';
import {extname,resolve,sep} from 'node:path';
import {fileURLToPath} from 'node:url';

const root=fileURLToPath(new URL('../../',import.meta.url));
const port=Number(process.argv[2]??4173);
const mime={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.mjs':'text/javascript; charset=utf-8','.json':'application/json; charset=utf-8','.md':'text/plain; charset=utf-8','.png':'image/png','.gif':'image/gif','.svg':'image/svg+xml'};
const allowed=['demos','assets','pipeline/rig'].map(p=>resolve(root,p)+sep);
createServer((req,res)=>{
  try {
    const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
    if(pathname==='/') {res.writeHead(302,{Location:'/demos/viewer/'}).end();return;}
    if(!['GET','HEAD'].includes(req.method)) {res.writeHead(405).end();return;}
    const path=resolve(root,'.'+(pathname.endsWith('/')?pathname+'index.html':pathname));
    if(!allowed.some(dir=>path.startsWith(dir))) {res.writeHead(403).end();return;}
    const stat=statSync(path);
    if(!stat.isFile()) {res.writeHead(404).end();return;}
    res.writeHead(200,{'Content-Type':mime[extname(path)]??'application/octet-stream','Content-Length':stat.size,'Cache-Control':'no-store'});
    if(req.method==='HEAD') res.end();
    else createReadStream(path).on('error',()=>res.destroy()).pipe(res);
  } catch {res.writeHead(404).end();}
}).listen(port,'127.0.0.1',()=>console.log('http://127.0.0.1:'+port+'/'));
