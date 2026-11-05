import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { DatabaseSync } from 'node:sqlite';
import { seedDemoActivity } from './demo-seed.mjs';
import { deepSeekChatCompletion, validateCanvasAction } from './deepseek-client.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../..');
const port = Number(process.env.PORT || 4177);
const db = new DatabaseSync(process.env.AURATEACH_DB_PATH || path.join(here, 'curio-demo.sqlite'));
const sessions = new Map();
const masterPrompt = fs.readFileSync(path.join(here, 'tutor-prompt.md'), 'utf8');

db.exec(`CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, alias TEXT NOT NULL, role TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(alias,role));
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, type TEXT NOT NULL, alias TEXT NOT NULL, role TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '', at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS models(id TEXT PRIMARY KEY, name TEXT NOT NULL, topic TEXT NOT NULL, url TEXT NOT NULL);
INSERT OR IGNORE INTO models(id,name,topic,url) VALUES
 ('escuela-scan','Modelo escolar','Exploración 3D','/9_13_2025-mejorado.glb'),
 ('maceta','Maceta','Biología y ambiente','/flower-pot.glb'),
 ('colonia-hongos','Colonia de hongos','Biología y ambiente','/mushroom_colony_LOD0.glb'),
 ('lapicero','Lapicero','Ingeniería y materiales','/demo-lapicero/lapicero.glb'),
 ('lapicero-corte','Lapicero diseccionado','Ingeniería y materiales','/demo-lapicero/lapicero-exploded.glb');`);
function hasColumn(table, column) { return db.prepare(`PRAGMA table_info(${table})`).all().some(row => row.name === column); }
if (!hasColumn('events', 'user_id')) db.exec('ALTER TABLE events ADD COLUMN user_id TEXT');
if (!hasColumn('events', 'question')) db.exec('ALTER TABLE events ADD COLUMN question TEXT NOT NULL DEFAULT \'\'');
if (!hasColumn('events', 'is_synthetic')) db.exec('ALTER TABLE events ADD COLUMN is_synthetic INTEGER NOT NULL DEFAULT 0');
if (!hasColumn('users', 'is_synthetic')) db.exec('ALTER TABLE users ADD COLUMN is_synthetic INTEGER NOT NULL DEFAULT 0');
for (const [column, definition] of [['thumbnail', "TEXT NOT NULL DEFAULT ''"], ['parts_json', "TEXT NOT NULL DEFAULT '[]'"], ['disassemblable', 'INTEGER NOT NULL DEFAULT 0']]) {
  if (!hasColumn('models', column)) db.exec(`ALTER TABLE models ADD COLUMN ${column} ${definition}`);
}
db.exec(`INSERT OR IGNORE INTO users(id,alias,role,created_at)
SELECT lower(hex(randomblob(16))),alias,role,MIN(at) FROM events GROUP BY alias,role;
UPDATE events SET user_id=(SELECT users.id FROM users WHERE users.alias=events.alias AND users.role=events.role LIMIT 1) WHERE user_id IS NULL;`);

seedDemoActivity(db, { enabled: process.env.AURATEACH_SEED_DEMO !== 'false' });

const categoryNames = { anatomia: 'Biología y ambiente', electronica: 'Electrónica', mecanica: 'Mecánica e ingeniería' };
const manualParts = {
  'Barril principal': 'Cuerpo exterior que sostiene los componentes del lapicero.',
  'Cartucho de tinta': 'Contiene la tinta que recorre el interior del lapicero.',
  'Depósito de tinta': 'Parte del cartucho donde se almacena la tinta.',
  'Clip · curva': 'Curva flexible que permite sujetar el lapicero a una tela o cuaderno.',
  'Cono frontal': 'Pieza delantera que guía y protege la punta.',
  'Corona pulsable': 'Mecanismo superior que acciona la salida de la punta.',
  'Agarre estriado': 'Superficie texturada que mejora el agarre de los dedos.'
};
function partId(name, index) { return `${name.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-')}-${index}`; }
function readGlbNodes(glbPath) {
  try {
    const bytes = fs.readFileSync(glbPath);
    if (bytes.readUInt32LE(0) !== 0x46546c67) return [];
    const jsonLength = bytes.readUInt32LE(12);
    const json = JSON.parse(bytes.toString('utf8', 20, 20 + jsonLength).replace(/\0+$/g, ''));
    return (json.nodes || []).map(node => node.name).filter(Boolean);
  } catch { return []; }
}
function registerLibraryModels() {
  const assets = path.join(root, '3d_lab_aurateach/assets');
  const files = [];
  const walk = dir => { for (const entry of fs.readdirSync(dir, { withFileTypes: true })) { const full = path.join(dir, entry.name); if (entry.isDirectory()) walk(full); else if (entry.name.toLowerCase().endsWith('.glb')) files.push(full); } };
  walk(assets);
  const upsert = db.prepare(`INSERT INTO models(id,name,topic,url,thumbnail,parts_json,disassemblable) VALUES(?,?,?,?,?,?,?)
    ON CONFLICT(id) DO UPDATE SET name=excluded.name,topic=excluded.topic,url=excluded.url,thumbnail=excluded.thumbnail,
    parts_json=CASE WHEN excluded.parts_json='[]' THEN models.parts_json ELSE excluded.parts_json END,
    disassemblable=MAX(models.disassemblable,excluded.disassemblable)`);
  for (const file of files) {
    const relative = path.relative(assets, file).split(path.sep).join('/');
    const base = relative.replace(/\.glb$/i, '');
    const id = `lab-${base.replaceAll('/', '-')}`;
    const leaf = path.basename(base).replaceAll('_', ' ').replaceAll('-', ' ');
    const name = leaf.replace(/\b\w/g, char => char.toLocaleUpperCase('es'));
    const category = relative.split('/')[0];
    const topic = categoryNames[category] || 'Exploración 3D';
    const thumbnail = `/prototipo/rodrigo-demos/model-thumbnails/${id}.png`;
    upsert.run(id, name, topic, `/3d_lab_aurateach/assets/${relative}`, thumbnail, '[]', 0);
  }
  const pen = path.join(root, 'demo-lapicero/lapicero.glb');
  const names = readGlbNodes(pen);
  let preparedPositions = new Map();
  try { const manifest = JSON.parse(fs.readFileSync(path.join(root, 'demo-lapicero/lapicero-parts.json'), 'utf8')); preparedPositions = new Map((manifest.parts || []).map(part => [part.nodeName, part])); } catch {}
  const parts = names.map((nodeName, index) => { const position = preparedPositions.get(nodeName) || {}; return { id: partId(nodeName, index), nodeName, label: nodeName, description: manualParts[nodeName] || `Componente del lapicero. Observa su forma y cómo se conecta con las otras piezas.`, originPosition: position.originPosition || null, explodedPosition: position.explodedPosition || null }; });
  const thumbnail = '/prototipo/rodrigo-demos/model-thumbnails/lapicero.png';
  db.prepare(`UPDATE models SET thumbnail=?,parts_json=?,disassemblable=1 WHERE id='lapicero'`).run(thumbnail, JSON.stringify(parts));
  db.prepare(`DELETE FROM models WHERE id='lapicero-corte'`).run();
  db.exec(`UPDATE models SET thumbnail='/prototipo/rodrigo-demos/model-thumbnails/escuela-scan.png' WHERE id='escuela-scan';
           UPDATE models SET thumbnail='/prototipo/rodrigo-demos/model-thumbnails/maceta.png' WHERE id='maceta';
           UPDATE models SET thumbnail='/prototipo/rodrigo-demos/model-thumbnails/colonia-hongos.png' WHERE id='colonia-hongos';`);
}
registerLibraryModels();

const mime = { '.html':'text/html; charset=utf-8', '.css':'text/css; charset=utf-8', '.js':'text/javascript; charset=utf-8', '.mjs':'text/javascript; charset=utf-8', '.glb':'model/gltf-binary', '.svg':'image/svg+xml', '.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg', '.webp':'image/webp' };
function send(res, status, data, type = 'application/json; charset=utf-8', headers = {}) { res.writeHead(status, { 'content-type': type, ...headers }); res.end(type.startsWith('application/json') ? JSON.stringify(data) : data); }
async function readBody(req) { let raw = ''; for await (const chunk of req) { raw += chunk; if (raw.length > 8_000_000) throw Error('Body too large'); } return raw ? JSON.parse(raw) : {}; }
function userFor(req) { const sid = (req.headers.cookie || '').split(';').map(x => x.trim()).find(x => x.startsWith('curio_sid='))?.slice(10); return sid ? sessions.get(sid) : null; }
function log(user, type, detail = '', model = '', question = '') {
  db.prepare('INSERT INTO events(type,alias,role,detail,model,at,user_id,question) VALUES(?,?,?,?,?,?,?,?)')
    .run(type, user.alias, user.role, String(detail).slice(0, 2000), String(model).slice(0, 300), new Date().toISOString(), user.id, String(question).slice(0, 2000));
}
function partsFor(model) { try { return JSON.parse(model?.parts_json || '[]'); } catch { return []; } }
const toolList = [{ type: 'function', function: { name: 'canvas_action', description: 'Enfoca una pieza verificada o agrega una indicación visual al modelo activo.', parameters: { type: 'object', properties: { action: { type: 'string', enum: ['zoom', 'arrow', 'focus_part', 'set_exploded', 'reset'] }, partId: { type: 'string' }, message: { type: 'string' }, value: { type: 'boolean' } }, required: ['action'] } } }];
async function handler(req, res) {
  if (req.method === 'OPTIONS') return send(res, 204, {});
  const url = new URL(req.url, `http://${req.headers.host}`);
  try {
    if (req.method === 'GET' && url.pathname === '/api/status') {
      return send(res, 200, { llmConfigured: Boolean(process.env.LLM_API_KEY), llmModel: process.env.LLM_MODEL || 'deepseek-flash' });
    }
    if (req.method === 'POST' && url.pathname === '/api/login') {
      const d = await readBody(req), alias = String(d.alias || 'Estudiante').trim().slice(0, 40) || 'Estudiante', role = d.role === 'teacher' ? 'teacher' : 'student';
      db.prepare('INSERT OR IGNORE INTO users(id,alias,role,created_at) VALUES(?,?,?,?)').run(randomUUID(), alias, role, new Date().toISOString());
      const account = db.prepare('SELECT id,alias,role FROM users WHERE alias=? AND role=?').get(alias, role), sid = randomUUID(); sessions.set(sid, account);
      return send(res, 200, { user: account }, 'application/json; charset=utf-8', { 'set-cookie': `curio_sid=${sid}; HttpOnly; SameSite=Lax; Path=/; Max-Age=28800` });
    }
    if (req.method === 'POST' && url.pathname === '/api/logout') {
      const sid = (req.headers.cookie || '').split(';').map(x => x.trim()).find(x => x.startsWith('curio_sid='))?.slice(10); if (sid) sessions.delete(sid);
      return send(res, 200, { ok: true }, 'application/json; charset=utf-8', { 'set-cookie': 'curio_sid=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0' });
    }
    if (req.method === 'GET' && url.pathname === '/api/models') {
      const rows = db.prepare(`SELECT m.id,m.name,m.topic,m.url,m.thumbnail,m.parts_json,m.disassemblable,COUNT(e.id) opens
        FROM models m LEFT JOIN events e ON e.type='model_open' AND e.model=m.id GROUP BY m.id ORDER BY opens DESC,m.name`).all();
      return send(res, 200, { models: rows.map(({ parts_json, ...m }) => ({ ...m, parts: JSON.parse(parts_json || '[]'), disassemblable: Boolean(m.disassemblable) })) });
    }
    if (req.method === 'POST' && url.pathname === '/api/model-open') {
      const user = userFor(req); if (!user) return send(res, 401, { error: 'Inicia sesión.' }); const data = await readBody(req);
      const model = db.prepare('SELECT id,name FROM models WHERE id=?').get(data.modelId); if (!model) return send(res, 404, { error: 'Modelo no encontrado.' });
      log(user, 'model_open', model.name, model.id); return send(res, 200, { ok: true });
    }
    if (req.method === 'POST' && url.pathname === '/api/event') {
      const user = userFor(req); if (!user) return send(res, 401, { error: 'Inicia sesión.' }); const data = await readBody(req);
      const allowed = new Set(['canvas_action', 'part_inspect', 'own_model_open']); if (!allowed.has(data.type)) return send(res, 400, { error: 'Tipo de actividad no permitido.' });
      log(user, data.type, data.detail || '', String(data.model || '').slice(0, 300)); return send(res, 200, { ok: true });
    }
    if (req.method === 'POST' && url.pathname === '/api/ask') {
      const user = userFor(req); if (!user) return send(res, 401, { error: 'Inicia sesión.' }); const data = await readBody(req);
      const question = String(data.question || '').trim().slice(0, 2000); if (!question) return send(res, 400, { error: 'Escribe una pregunta.' });
      const model = db.prepare('SELECT * FROM models WHERE id=?').get(String(data.modelId || '')) || null;
      const modelName = model?.name || String(data.model || 'Modelo propio').slice(0, 150), topic = model?.topic || 'Exploración de lo visible';
      const ownModel = Boolean(data.ownModel), image = typeof data.image === 'string' && /^data:image\/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$/.test(data.image) && data.image.length <= 2_500_000 ? data.image : '';
      log(user, 'question', question, model?.id || modelName, question);
      const apiKey = process.env.LLM_API_KEY, endpoint = process.env.LLM_API_URL || 'https://api.deepseek.com/chat/completions', llmModel = process.env.LLM_MODEL || 'deepseek-flash';
      const parts = model && !ownModel ? partsFor(model) : [];
      const selected = parts.find(part => part.id === data.selectedPart || part.nodeName === data.selectedPart);
      const annotationText = parts.length ? parts.map(part => `- ${part.id} (${part.label}): ${part.description}`).join('\n') : 'No hay piezas verificadas; limítate a lo que se ve en la imagen.';
      if (apiKey) {
        try {
          let instructions = masterPrompt.replace('{{MODEL}}', modelName).replace('{{TOPIC}}', topic).replace('{{ANNOTATIONS}}', annotationText);
          if (ownModel) instructions += '\n\nMODELO PROPIO: no des por hecho piezas ocultas ni intentes diseccionarlo. Basa la respuesta solo en la imagen enviada y describe incertidumbres.';
          if (selected) instructions += `\n\nPIEZA SELECCIONADA POR EL ESTUDIANTE: ${selected.label}. ${selected.description}`;
          const { response: upstream, result } = await deepSeekChatCompletion({ apiKey, endpoint, model: llmModel, instructions, question, image, tools: toolList });
          if (!upstream.ok) return send(res, 502, { error: 'DeepSeek no respondió. Revisa la API key y el saldo.' });
          const message = result.choices?.[0]?.message; let action = null; const call = message?.tool_calls?.[0];
          if (call?.function?.name === 'canvas_action') { try { action = validateCanvasAction(JSON.parse(call.function.arguments), { model, isOwnModel: ownModel, parts }); } catch {} }
          if (action) log(user, 'canvas_action', action.type, model?.id || '');
          return send(res, 200, { answer: message?.content || 'Mira el detalle que he señalado. ¿Qué observas?', action, mode: 'live' });
        } catch { return send(res, 502, { error: 'No se pudo conectar con DeepSeek.' }); }
      }
      const q = question.toLowerCase(); let action = null;
      if (!ownModel && model?.disassemblable && /separa|dise|interior|por dentro|corte/.test(q)) action = { type: 'set_exploded', value: true };
      else if (!ownModel && selected) action = { type: 'focus_part', partId: selected.id, message: selected.label };
      else if (/acerca|zoom|más cerca/.test(q)) action = { type: 'zoom' };
      else if (/señala|flecha|dónde está/.test(q)) action = { type: 'arrow', message: 'Observa esta zona' };
      return send(res, 200, { answer: `Buena pregunta sobre ${topic.toLowerCase()}. Observa el modelo: ¿qué detalle te da una pista para responderla?`, action, mode: 'simulated' });
    }
    if (req.method === 'GET' && url.pathname === '/api/dashboard') {
      const user = userFor(req); if (!user) return send(res, 401, { error: 'Inicia sesión.' }); if (user.role !== 'teacher') return send(res, 403, { error: 'Solo el docente puede ver este panel.' });
      const source = ['all', 'synthetic', 'real'].includes(url.searchParams.get('source')) ? url.searchParams.get('source') : 'all';
      const eventFilter = source === 'synthetic' ? ' AND is_synthetic=1' : source === 'real' ? ' AND is_synthetic=0' : '';
      const eventFilterE = eventFilter.replaceAll('is_synthetic', 'e.is_synthetic');
      const userFilter = source === 'synthetic' ? ' AND u.is_synthetic=1' : source === 'real' ? ' AND u.is_synthetic=0' : '';
      const since = new Date(Date.now() - 7 * 86400000).toISOString();
      const summary = {
        questions: db.prepare(`SELECT COUNT(*) n FROM events WHERE type='question'${eventFilter}`).get().n,
        opens: db.prepare(`SELECT COUNT(*) n FROM events WHERE type IN ('model_open','own_model_open')${eventFilter}`).get().n,
        students: db.prepare(`SELECT COUNT(*) n FROM users WHERE role='student'${userFilter}`).get().n,
        parts: db.prepare(`SELECT COUNT(*) n FROM events WHERE type='part_inspect'${eventFilter}`).get().n
      };
      const students = db.prepare(`SELECT u.id,u.alias,
        SUM(CASE WHEN e.type='question' THEN 1 ELSE 0 END) questions,
        SUM(CASE WHEN e.type IN ('model_open','own_model_open') THEN 1 ELSE 0 END) visits,
        MAX(e.at) lastSeen,
        SUM(CASE WHEN e.at>=? AND e.type IN ('question','model_open','own_model_open','part_inspect') THEN 1 ELSE 0 END) recent,
        u.is_synthetic isSynthetic
        FROM users u LEFT JOIN events e ON e.user_id=u.id${eventFilterE} WHERE u.role='student'${userFilter} GROUP BY u.id
        ORDER BY SUM(CASE WHEN e.type='question' THEN 1 ELSE 0 END)+SUM(CASE WHEN e.type IN ('model_open','own_model_open') THEN 1 ELSE 0 END) DESC,u.alias`).all(since);
      const maxScore = Math.max(1, ...students.map(x => x.questions + x.visits));
      for (const student of students) { student.activityScore = Math.round((student.questions + student.visits) / maxScore * 100); student.lowActivity = student.recent < 2; }
      const popular = db.prepare(`SELECT m.name,COUNT(e.id) opens FROM models m LEFT JOIN events e ON e.type='model_open' AND e.model=m.id${eventFilterE} GROUP BY m.id ORDER BY opens DESC,m.name LIMIT 8`).all();
      const questionRows = db.prepare(`SELECT e.question,e.alias,e.at,e.model,COALESCE(m.name,e.model) modelName,e.is_synthetic isSynthetic FROM events e LEFT JOIN models m ON m.id=e.model WHERE e.type='question' AND e.question<>''${eventFilterE} ORDER BY e.at DESC LIMIT 500`).all();
      const recent = db.prepare(`SELECT substr(at,1,10) day,SUM(CASE WHEN type='question' THEN 1 ELSE 0 END) questions,SUM(CASE WHEN type IN ('model_open','own_model_open') THEN 1 ELSE 0 END) visits FROM events WHERE at>=?${eventFilter} GROUP BY substr(at,1,10) ORDER BY day`).all(since);
      const byDay = new Map(recent.map(row => [row.day, row])), activity = [];
      for (let i=6;i>=0;i--) { const date = new Date(); date.setDate(date.getDate()-i); const key = date.toISOString().slice(0,10), row = byDay.get(key); activity.push({ day:key.slice(5), questions:row?.questions||0, visits:row?.visits||0 }); }
      return send(res, 200, { source, summary, students, popular, questions: questionRows, activity });
    }
    const pathname = decodeURIComponent(url.pathname), base = '/prototipo/rodrigo-demos';
    const filePath = pathname === '/' || pathname === base || pathname === `${base}/` ? 'prototipo/rodrigo-demos/index.html' : pathname === `${base}/aula` || pathname === `${base}/aula.html` ? 'prototipo/rodrigo-demos/aula.html' : pathname.startsWith(`${base}/`) ? pathname.slice(1) : pathname.replace(/^\/+/, '');
    const file = path.resolve(root, filePath); if (!file.startsWith(root + path.sep)) return send(res, 403, 'Forbidden', 'text/plain; charset=utf-8');
    fs.readFile(file, (err, content) => err ? send(res, 404, 'Not found', 'text/plain; charset=utf-8') : send(res, 200, content, mime[path.extname(file)] || 'application/octet-stream'));
  } catch (error) { console.error(error); return send(res, 400, { error: 'Solicitud inválida.' }); }
}
http.createServer(handler).listen(port, '0.0.0.0', () => console.log(`AuraTeach en http://localhost:${port}/prototipo/rodrigo-demos/aula.html`));
