import { createServer } from 'node:http';
import { createReadStream, existsSync, readFileSync } from 'node:fs';
import { extname, join, normalize } from 'node:path';

const ROOT = new URL('.', import.meta.url).pathname;
const KEY = process.env.DEEPSEEK_API_KEY;
const MIME = { '.html':'text/html; charset=utf-8', '.glb':'model/gltf-binary', '.mjs':'text/javascript; charset=utf-8', '.css':'text/css; charset=utf-8' };
const html = readFileSync(join(ROOT, 'index.html'));

const server = createServer(async (req, res) => {
  if (req.method === 'POST' && req.url === '/api/ask') {
    if (!KEY) { res.writeHead(503, {'content-type':'application/json'}); return res.end(JSON.stringify({error:'Falta DEEPSEEK_API_KEY en el entorno.'})); }
    let raw='';
    for await (const chunk of req) { raw += chunk; if (raw.length > 9_000_000) { res.writeHead(413); return res.end(); } }
    try {
      const body=JSON.parse(raw);
      if (typeof body.question !== 'string' || body.question.length > 2000) throw new Error('Pregunta no válida.');
      const content=[{type:'text',text:`Pregunta: ${body.question}\n\nNodos del modelo (nombres y centros en coordenadas locales): ${JSON.stringify(body.parts ?? []).slice(0,12000)}\n\nResponde en español. Basa las ubicaciones solo en la imagen y los nodos proporcionados. Si no puedes identificar una pieza con confianza, dilo y no propongas un punto inventado.`}];
      if (typeof body.image === 'string' && /^data:image\/(png|jpeg|webp);base64,/.test(body.image)) content.push({type:'image_url',image_url:{url:body.image,detail:'high'}});
      const response=await fetch('https://api.deepseek.com/chat/completions',{method:'POST',headers:{'authorization':`Bearer ${KEY}`,'content-type':'application/json'},body:JSON.stringify({model:'deepseek-flash',stream:false,messages:[{role:'system',content:'Eres un tutor que explica modelos 3D escaneados. No afirmes conocer estructuras internas que no sean visibles. Usa guide_model para proponer una ubicación solo si está respaldada por la imagen o por un nodo nombrado.'},{role:'user',content}],tools:[{type:'function',function:{name:'guide_model',description:'Entrega explicación y, si hay una pieza localizable, una acción para enfocar y señalarla.',parameters:{type:'object',properties:{explanation:{type:'string'},follow_up:{type:'string'},anchor:{type:'array',items:{type:'number'},minItems:3,maxItems:3},label:{type:'string'},zoom:{type:'number'}},required:['explanation','follow_up','anchor','label','zoom'],additionalProperties:false}}}],tool_choice:'auto',max_tokens:500})});
      const data=await response.json(); if(!response.ok) throw new Error(data.error?.message ?? `DeepSeek respondió ${response.status}`);
      const msg=data.choices?.[0]?.message; let action=null;
      const call=msg?.tool_calls?.find(x=>x.function?.name==='guide_model');
      if(call){try{const a=JSON.parse(call.function.arguments);if(Array.isArray(a.anchor)&&a.anchor.length===3&&a.anchor.every(Number.isFinite))action={anchor:a.anchor.map(v=>Math.max(-1000,Math.min(1000,v))),label:String(a.label).slice(0,80),zoom:Math.max(10,Math.min(1500,Number(a.zoom)||100))};res.writeHead(200,{'content-type':'application/json'});return res.end(JSON.stringify({text:String(a.explanation||'').slice(0,4000),follow_up:String(a.follow_up||'').slice(0,500),action}));}catch{}}
      res.writeHead(200,{'content-type':'application/json'});res.end(JSON.stringify({text:msg?.content||'No pude preparar una explicación.',follow_up:'¿Qué detalle te gustaría explorar?',action}));
    } catch(e) { res.writeHead(400,{'content-type':'application/json'});res.end(JSON.stringify({error:e.message})); }
    return;
  }
  const path=req.url==='/'?'/index.html':decodeURIComponent(req.url.split('?')[0]);
  const file=normalize(join(ROOT,path));
  if (!file.startsWith(ROOT) || !existsSync(file)) { res.writeHead(404);return res.end('Not found'); }
  res.writeHead(200,{'content-type':MIME[extname(file)]??'application/octet-stream'});createReadStream(file).pipe(res);
});
server.listen(Number(process.env.PORT)||8000,'127.0.0.1',()=>console.log(`Demo en http://localhost:${process.env.PORT||8000}`));
