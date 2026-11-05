import { readFileSync, writeFileSync } from "node:fs";
import * as k from "../.agents/skills/anatomy/kit/iso-kit.mjs";
import * as G from "../.agents/skills/anatomy/kit/lathe.mjs";
import { kitScript } from "../.agents/skills/anatomy/scripts/inline-kit.mjs";

// Figure: a push-button ballpoint pen on a small service cradle.
// The outer shell is lifted to expose the refill, spring and nose assembly.
const W = 700, H = 410;
const P = k.fitProjection([...k.boxCorners({x:-148,y:-40,w:296,d:80,r:8},-10,0),[-132,0,38],[116,0,38]],W,H,{pad:28,azimuth:42});
const S=(p,s)=>k.solidSvg(p,s), L=(d,s)=>k.lineSvg(d,s), D=(p,s)=>k.dotsSvg(p,s), at=p=>k.iso(p,P);
const axis=G.frameOf([0,0,28],[1,0,0],[0,1,0],[0,0,1]);
const round=(s0,s1,r,options={})=>G.solidOf([[s0,0],[s0,r],[s1,r],[s1,0]],axis,P,options);
const out=[];
const base={x:-148,y:-40,w:296,d:80,r:8};
out.push(`<path class="iso-halo" d="${k.haloOf(base,-10,10,P)}"/>`);
// Cradle: feet, plate, two saddles, and fasteners.
for(const [x,y] of k.corners(base,14)){
  out.push(S(k.cylinder(x,y,7,-10,2,P,24),{tone:"lo"}));
  out.push(S(k.cylinder(x,y,5,-8,8,P,24),{tone:"mid"}));
  out.push(D([at([x,y,0])],{size:.6,tone:"hi"}));
}
out.push(S(k.slabOf(base,-5,5,P,8,1),{tone:"mid"}));
out.push(L(k.planOutline(k.insetPlan(base,4),0,P),{tone:"faint"}));
const ruler={x:-128,y:25,w:256,d:7,r:1};
out.push(S(k.slabOf(ruler,0,.8,P,4),{tone:"lo",crease:"none"}));
const ticks=k.topTicks(ruler.x+4,ruler.x+ruler.w-4,4,5,ruler.y+.8,.8,[2,3.6],P);
out.push(L(ticks.minor,{tone:"faint"}),L(ticks.major,{tone:"mid"}));
for(const x of [-72,72]){
  out.push(S(k.slabOf({x:x-8,y:-20,w:16,d:40,r:4},0,8,P,5,.6),{tone:"mid"}));
  out.push(S(k.cylinder(x,0,7,8,2,P,24),{tone:"hi"}));
  out.push(D([at([x-4,-12,8]),at([x+4,-12,8]),at([x-4,12,8]),at([x+4,12,8])],{size:.45,tone:"lo"}));
}

// Nose cone and writing point: concentric turned parts share the pen axis.
out.push(S(round(-126,-112,7),{tone:"mid"}));
out.push(S(round(-126,-124,3.1),{tone:"hi",crease:"lo"}));
out.push(S(round(-140,-126,1.35),{tone:"hi",lit:true}));
out.push(L(k.sideRing([-126,0,28],3.1,"x",P,24),{tone:"lo"}));
out.push(L(k.sideRing([-124,0,28],1.35,"x",P,20),{tone:"faint"}));

// Rubber grip: turned sleeve with fine longitudinal flutes and two end collars.
out.push(S(round(-112,-91,8.2),{tone:"hi"}));
out.push(L(G.ribsOf(axis,-110,-93,8.25,28,P,{fade:[.04,.35],seams:true}).map(x=>x.d).join(""),{tone:"lo"}));
for(const s of [-112,-91]) out.push(L(k.sideRing([s,0,28],8.15,"x",P,32),{tone:"faint"}));
out.push(S(round(-114,-112,7.6),{tone:"mid"}),S(round(-91,-89,7.6),{tone:"mid"}));

// The ink refill and the spring remain in the lower channel.
out.push(S(round(-123,61,1.55),{tone:"hi",lit:true}));
out.push(S(round(57,62,2.3),{tone:"mid"}));
out.push(S(round(62,69,2.8),{tone:"mid"}));
out.push(L(k.coil(-88,-74,[0,28],4.1,8,"x",P,20).back,{tone:"lo"}));
out.push(S(round(-76,-72,2.2),{tone:"mid"}));
out.push(L(k.coil(-88,-74,[0,28],4.1,8,"x",P,20).front,{tone:"hi"}));
// Cartridge seams and the ink reservoir window.
for(const s of [-102,-74,16,44]) out.push(L(k.sideRing([s,0,28],1.6,"x",P,20),{tone:"faint"}));
out.push(L(k.sideRing([4,0,28],2.05,"x",P,20),{tone:"lo"}));

// Rear barrel halves; the upper half lifts away in the open view.
const shell=(a,b,r,tone)=>S(round(a,b,r,{steps:72}),{tone,crease:"lo"});
out.push(`<g data-shell="lower">${shell(-89,89,9,"blue")}${L(k.sideRing([-89,0,28],8.9,"x",P,32),{tone:"lo"})}${L(k.sideRing([89,0,28],8.9,"x",P,32),{tone:"lo"})}</g>`);
const topShell=[];
topShell.push(shell(-89,89,9,"blue"));
topShell.push(L(k.sideRing([-89,0,28],8.9,"x",P,32),{tone:"lo"}));
topShell.push(L(k.sideRing([89,0,28],8.9,"x",P,32),{tone:"lo"}));
// Small moulded seam bands and two raised ribs on the cap.
for(const s of [-84,-81,82,85]) topShell.push(L(k.sideRing([s,0,28],9,"x",P,32),{tone:"faint"}));
for(const s of [-78,-72,72,78]) topShell.push(S(round(s,s+1.2,9.7),{tone:"hi"}));
out.push(`<g data-shell="upper" style="transform:translateY(-30px);transition:transform 650ms cubic-bezier(.2,.75,.25,1)">${topShell.join("")}</g>`);

// Pocket clip: a raised base, neck, curved return and riveted keeper.
const clipPlan={x:24,y:6,w:57,d:3.2,r:1.5};
out.push(S(k.slabOf({x:75,y:4,w:12,d:9,r:2},23,3,P,4,.5),{tone:"mid"}));
out.push(S(k.slabOf({x:72,y:5,w:4,d:5,r:1.5},24,14,P,4,.4),{tone:"hi"}));
out.push(S(k.slabOf(clipPlan,37,2.8,P,8,.6),{tone:"hi"}));
out.push(L(k.planOutline(k.insetPlan(clipPlan,.7),39.8,P),{tone:"lo"}));
out.push(S(k.slabOf({x:23,y:6,w:5,d:3.2,r:1.4},36,3.4,P,4,.5),{tone:"mid"}));
out.push(D([at([79,5,26]),at([82,5,26])],{size:.55,tone:"lo"}));

// Click mechanism: stepped end cap, plunger stem, crown and tactile grooves.
out.push(S(round(89,98,9),{tone:"mid"}));
out.push(S(round(98,106,7.4),{tone:"hi"}));
out.push(S(round(106,113,5.8),{tone:"mid"}));
out.push(S(round(113,118,6.3),{tone:"hi"}));
for(let i=0;i<16;i++){
  const a=(i/16)*Math.PI*2;
  const y=Math.cos(a)*6.2,z=28+Math.sin(a)*6.2;
  out.push(L(k.segment([114,y,z],[117,y,z],P),{tone:i%2?"lo":"faint"}));
}
out.push(L(k.sideRing([98,0,28],7.4,"x",P,28),{tone:"lo"}));
out.push(L(k.sideRing([106,0,28],5.8,"x",P,28),{tone:"faint"}));
out.push(L(k.sideRing([113,0,28],6.3,"x",P,28),{tone:"lo"}));

const fig=k.figureSvg({width:W,height:H,label:"Lapicero de pulsador isométrico sobre un soporte de reparación. La vista abierta enseña la punta, el cartucho de tinta, el resorte de retorno, el cuerpo, el clip y el pulsador.",body:out,standalone:false});
const live=`
const stage=document.querySelector('[data-pen]');
const button=document.querySelector('[data-toggle]');
const upper=stage.querySelector('[data-shell="upper"]');
let open=true;
button.addEventListener('click',()=>{
  open=!open;
  upper.style.transform=open?'translateY(-30px)':'translateY(0px)';
  button.textContent=open?'Cerrar carcasa':'Abrir carcasa';
  button.setAttribute('aria-pressed',String(open));
  document.querySelector('[data-readout]').textContent=open?'Carcasa levantada · mecanismo visible':'Lapicero ensamblado';
});
`;
const glb=readFileSync(new URL("./lapicero.glb",import.meta.url)).toString("base64");
const exploded=readFileSync(new URL("./lapicero-exploded.glb",import.meta.url)).toString("base64");
const viewer=`<section class="glb-explorer" aria-labelledby="glb-title"><h2 id="glb-title">Explora el modelo 3D</h2><p>Arrastra para rotar · rueda o pellizca para acercar</p><model-viewer data-pen-model src="data:model/gltf-binary;base64,${glb}" alt="Modelo 3D de un lapicero" camera-controls touch-action="pan-y" interaction-prompt="auto" shadow-intensity="1" exposure="1" camera-orbit="35deg 70deg 330m" min-camera-orbit="auto auto 25m" max-camera-orbit="auto auto 1000m"></model-viewer><button class="glb-toggle" type="button" aria-pressed="false">Desarmar lapicero</button><a class="glb-download" download="lapicero.glb" href="data:model/gltf-binary;base64,${glb}">Descargar GLB</a><script type="module" src="https://cdn.jsdelivr.net/npm/@google/model-viewer/dist/model-viewer.min.js"></script><script>const model=document.querySelector('[data-pen-model]'),toggle=document.querySelector('.glb-toggle');let apart=false;toggle.addEventListener('click',()=>{apart=!apart;model.src=apart?'data:model/gltf-binary;base64,${exploded}':'data:model/gltf-binary;base64,${glb}';toggle.textContent=apart?'Ensamblar lapicero':'Desarmar lapicero';toggle.setAttribute('aria-pressed',String(apart));model.cameraOrbit=apart?'35deg 70deg 470m':'35deg 70deg 330m';});</script></section>`;
const card=k.plateHtml({fig:"Fig 1",title:"Anatomía de un lapicero",hint:"Mecanismo de pulsador · vista isométrica",readout:"Carcasa levantada · mecanismo visible",keys:[{mark:"blue",label:"Carcasa"},{mark:"lit",label:"Punta y cartucho"},{mark:"raised",label:"Mecanismo"}],caption:"Al pulsar, el mecanismo avanza el cartucho; el resorte lo devuelve al soltar. El corte deja visible el recorrido de la tinta hasta la punta.",body:`<div data-pen class="iso-stage pen-stage">${fig}</div><button data-toggle type="button" aria-pressed="true">Cerrar carcasa</button><p class="parts-note"><b>Piezas:</b> punta · cono · agarre estriado · cartucho · resorte · barril · clip · pulsador</p>${viewer}`});
const upload=`<section style="margin:28px 24px;padding:22px 24px;border-top:1px solid #dededb;text-align:left"><h2 style="font-size:19px;color:#252522">Carga otro modelo GLB</h2><p style="color:#74746f;font-size:13px">Selecciona un archivo .glb de tu equipo y explóralo aquí.</p><label for="glb-file" style="display:inline-block;padding:9px 14px;border:1px solid #b8b8b2;border-radius:8px;background:#fff;cursor:pointer">Seleccionar archivo GLB</label><input id="glb-file" type="file" accept=".glb,model/gltf-binary" style="position:absolute;width:1px;height:1px;opacity:0"><span data-file-name style="margin-left:10px;color:#62625d;font-size:13px">No hay archivo seleccionado</span><model-viewer data-upload-viewer alt="Vista 3D del archivo GLB seleccionado" camera-controls touch-action="pan-y" shadow-intensity="1" exposure="1" camera-orbit="35deg 70deg 330m" min-camera-orbit="auto auto 1m" max-camera-orbit="auto auto 1000m" style="display:block;width:100%;height:420px;margin-top:16px;border-radius:14px;background:#f1f1ed"></model-viewer><p data-upload-status role="status" aria-live="polite" style="color:#62625d;font-size:13px">Selecciona un GLB para comenzar.</p><script>const input=document.querySelector('#glb-file'),mv=document.querySelector('[data-upload-viewer]'),name=document.querySelector('[data-file-name]'),status=document.querySelector('[data-upload-status]');let objectUrl;input.addEventListener('change',()=>{const file=input.files?.[0];if(!file)return;if(objectUrl)URL.revokeObjectURL(objectUrl);objectUrl=URL.createObjectURL(file);mv.src=objectUrl;window.activeTutorModel=mv;name.textContent=file.name;status.textContent='Cargando modelo…';file.arrayBuffer().then(buf=>{const v=new DataView(buf);if(v.getUint32(0,true)!==0x46546c67)return;const len=v.getUint32(12,true),json=JSON.parse(new TextDecoder().decode(new Uint8Array(buf,20,len)).replace(/\u0000+$/,''));window.loadedGlbParts=(json.nodes||[]).filter(n=>n.name).map(n=>({name:n.name,center:n.translation||[0,0,0]}));});});mv.addEventListener('load',()=>status.textContent='Modelo listo · arrastra para rotar y pellizca para acercar.');mv.addEventListener('error',()=>status.textContent='No se pudo cargar el archivo. Comprueba que sea un GLB válido.');window.addEventListener('beforeunload',()=>{if(objectUrl)URL.revokeObjectURL(objectUrl);});</script></section>`;
const tutor=`<section style="margin:28px 24px;padding:22px 24px;border-top:1px solid #dededb;text-align:left"><h2 style="font-size:19px;color:#252522">Pregunta al guía del modelo</h2><p style="color:#74746f;font-size:13px">Prueba: “¿Qué hace el resorte?” o “¿de qué está hecha la punta?”</p><form data-tutor-form style="display:flex;gap:8px;flex-wrap:wrap"><input data-tutor-question aria-label="Pregunta sobre el lapicero" placeholder="Escribe tu pregunta…" style="flex:1;min-width:180px;padding:10px;border:1px solid #c8c8c2;border-radius:8px"><button type="submit" style="padding:9px 14px">Preguntar</button><button type="button" data-tutor-mic aria-label="Preguntar por voz" style="padding:9px 14px">🎙 Hablar</button></form><p data-tutor-answer role="status" aria-live="polite" style="min-height:48px;color:#30302e">Elige una pregunta para enfocar una pieza y escuchar una explicación.</p><p data-tutor-follow style="color:#555;font-size:13px"></p><script>
const tutorModel=window.activeTutorModel||document.querySelector('[data-pen-model]'),tutorForm=document.querySelector('[data-tutor-form]'),tutorInput=document.querySelector('[data-tutor-question]'),tutorAnswer=document.querySelector('[data-tutor-answer]'),tutorMic=document.querySelector('[data-tutor-mic]'),tutorFollow=document.querySelector('[data-tutor-follow]');let currentHotspot;
const topics=[{terms:['resorte','muelle','devolver','retorno'],title:'Resorte de retorno',x:-50,text:'El resorte almacena energía cuando el mecanismo del pulsador se comprime y empuja el cartucho de vuelta al soltarlo. Es una pieza de acero elástico; su fuerza depende del diámetro del alambre y de cuántas espiras tiene.',follow:'¿Qué cambiaría si el resorte fuera más rígido?',pos:'-50 0 4'},{terms:['tinta','cartucho','deposito','depósito'],title:'Cartucho de tinta',x:5,text:'El cartucho contiene la tinta y la conduce hacia la punta. En este modelo se distinguen el depósito y el tubo estrecho que alimenta la bola; la tinta debe fluir sin derramarse cuando el lapicero se mueve.',follow:'¿Por qué crees que la tinta no sale libremente por el cartucho?',pos:'5 0 3'},{terms:['punta','bola','escribir','escritura'],title:'Punta de escritura',x:-110,text:'La punta guía una pequeña bola metálica. Al deslizarse sobre el papel, la bola gira, recoge tinta del cartucho y la deposita en la superficie. El ajuste entre bola y alojamiento controla el flujo.',follow:'¿Cómo cambiaría el trazo con una bola más grande?',pos:'-110 0 2'},{terms:['agarre','goma','estrias','estrías'],title:'Agarre estriado',x:-75,text:'El agarre de elastómero aumenta la fricción entre los dedos y el lapicero. Las estrías ayudan a sujetarlo con menos fuerza y hacen más cómodo escribir durante más tiempo.',follow:'¿Qué ventaja tendría una superficie lisa?',pos:'-75 0 5'},{terms:['clip','bolsillo'],title:'Clip',x:60,text:'El clip de acero flexible sujeta el lapicero a un bolsillo o cuaderno. Su forma deja una pequeña separación para insertar la tela, mientras la elasticidad lo mantiene en su sitio.',follow:'¿Qué parte del clip debe flexionarse sin deformarse?',pos:'60 0 8'},{terms:['plastico','plástico','material','materiales','acero'],title:'Materiales',x:0,text:'La carcasa y el pulsador suelen ser de plástico moldeado, ligero y fácil de fabricar. El resorte y la bola de la punta son metálicos porque necesitan elasticidad o resistencia al desgaste; el agarre usa un material más blando.',follow:'¿Qué material elegirías para que el lapicero dure más?',pos:'0 0 8'}];
async function teach(question){if(!question){tutorAnswer.textContent='Escribe o dicta una pregunta.';return;}tutorAnswer.textContent='Analizando el modelo…';tutorFollow.textContent='';tutorModel=window.activeTutorModel||tutorModel;const parts=window.loadedGlbParts||['Punta cónica de escritura','Cono frontal','Agarre estriado','Barril principal','Cartucho de tinta','Depósito de tinta','Resorte de retorno','Clip','Émbolo del pulsador','Corona pulsable'];let image=null;try{if(typeof tutorModel.toDataURL==='function')image=tutorModel.toDataURL('image/jpeg');}catch{}try{const r=await fetch('/api/ask',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({question,parts,image})});const data=await r.json();if(!r.ok)throw Error(data.error||'No se pudo conectar con el agente.');tutorAnswer.textContent=data.text||'No recibí una explicación.';tutorFollow.textContent=data.follow_up||'';if(data.action){const [x,y,z]=data.action.anchor;tutorModel.cameraTarget=[x,y,z].join(' ');tutorModel.cameraOrbit='35deg 70deg '+data.action.zoom+'m';if(currentHotspot)currentHotspot.remove();currentHotspot=document.createElement('button');currentHotspot.slot='hotspot-focus';currentHotspot.dataset.position=[x,y,z].join(' ');currentHotspot.dataset.normal='0 0 1';currentHotspot.textContent='➤ '+data.action.label;currentHotspot.setAttribute('aria-label','Pieza enfocada: '+data.action.label);currentHotspot.style.cssText='border:0;border-radius:16px;padding:8px 12px;background:#7048e8;color:white;font-weight:700;box-shadow:0 2px 10px #0004;white-space:nowrap';tutorModel.append(currentHotspot);}if('speechSynthesis'in window){speechSynthesis.cancel();speechSynthesis.speak(new SpeechSynthesisUtterance(data.text));}}catch(e){tutorAnswer.textContent=e.message.includes('Failed to fetch')?'No se pudo conectar. Inicia server.mjs y configura DEEPSEEK_API_KEY.':e.message;}}
tutorForm.addEventListener('submit',e=>{e.preventDefault();teach(tutorInput.value.trim())});tutorMic.addEventListener('click',()=>{const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR){tutorAnswer.textContent='El reconocimiento de voz no está disponible en este navegador. Puedes escribir tu pregunta.';return;}const rec=new SR();rec.lang='es-ES';rec.onresult=e=>{tutorInput.value=e.results[0][0].transcript;teach(tutorInput.value)};rec.onerror=()=>tutorAnswer.textContent='No pude entender el audio. Intenta de nuevo o escribe la pregunta.';rec.start();});
</script></section>`;
const html=k.pageHtml({title:"Anatomía de un lapicero",theme:"light",body:card+upload+tutor,script:kitScript()+live}).replace('<html lang="en">','<html lang="es">').replace('</style>',`.glb-explorer{margin:28px 24px 22px;padding-top:22px;border-top:1px solid #dededb;text-align:left}.glb-explorer h2{margin:0 0 6px;font-size:19px;color:#252522}.glb-explorer p{margin:0 0 14px;color:#74746f;font-size:13px}.glb-explorer model-viewer{display:block;width:100%;height:420px;border-radius:14px;background:radial-gradient(ellipse at 50% 48%,#fff 0%,#f1f1ed 72%,#e9e9e4 100%);--poster-color:transparent}.glb-toggle{margin:14px 12px 0 0;padding:9px 14px;border:1px solid #b8b8b2;border-radius:8px;background:#fff;color:#252522;cursor:pointer}.glb-download{display:inline-block;margin-top:12px;color:#3e5d9d;font-size:13px;text-decoration:underline}@media(max-width:600px){.glb-explorer{margin:20px 14px 16px}.glb-explorer model-viewer{height:320px}}\n</style>`);
writeFileSync(new URL("./index.html",import.meta.url),html);
console.log("wrote demo-lapicero/index.html");
