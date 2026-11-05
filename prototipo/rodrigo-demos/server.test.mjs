import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { seedDemoActivity } from './demo-seed.mjs';

function demoDb() {
  const db = new DatabaseSync(':memory:');
  db.exec(`CREATE TABLE users(id TEXT PRIMARY KEY,alias TEXT,role TEXT,created_at TEXT,is_synthetic INTEGER DEFAULT 0);
    CREATE TABLE events(id INTEGER PRIMARY KEY,type TEXT,alias TEXT,role TEXT,detail TEXT,model TEXT,at TEXT,user_id TEXT,question TEXT,is_synthetic INTEGER DEFAULT 0);`);
  return db;
}

test('seed de estudiantes de demostración produce actividad variada en 14 días y es idempotente', () => {
  const db = demoDb(), now = Date.UTC(2026, 10, 5, 12);
  assert.equal(seedDemoActivity(db, { now }), true);
  assert.equal(seedDemoActivity(db, { now }), false);
  assert.equal(db.prepare("SELECT COUNT(*) n FROM users WHERE is_synthetic=1").get().n, 8);
  assert.equal(db.prepare("SELECT COUNT(*) n FROM users WHERE is_synthetic=0").get().n, 0);
  assert.equal(db.prepare("SELECT COUNT(*) n FROM events WHERE type='model_open' AND is_synthetic=1").get().n, 37);
  assert.equal(db.prepare("SELECT COUNT(*) n FROM events WHERE type='question' AND is_synthetic=1").get().n, 28);
  assert.equal(db.prepare("SELECT COUNT(*) n FROM events WHERE type='part_inspect' AND is_synthetic=1").get().n, 10);
  assert.equal(db.prepare('SELECT COUNT(*) n FROM events WHERE is_synthetic=0').get().n, 0);
  const bounds = db.prepare('SELECT MIN(at) first,MAX(at) last FROM events').get();
  assert.ok(Date.parse(bounds.first) >= now - 14 * 86400000);
  assert.ok(Date.parse(bounds.last) <= now);
  const participation = db.prepare(`SELECT u.alias,COUNT(CASE WHEN e.type='question' THEN 1 END) questions,
    COUNT(CASE WHEN e.type='model_open' THEN 1 END) visits FROM users u LEFT JOIN events e ON e.user_id=u.id
    WHERE u.is_synthetic=1 GROUP BY u.id ORDER BY questions+visits DESC`).all();
  assert.ok(participation[0].questions + participation[0].visits > participation.at(-1).questions + participation.at(-1).visits);
  assert.ok(participation.some(student => student.visits === 1), 'includes a student with very recent/low participation');
  db.close();
});

test('seed se puede desactivar para entornos sin datos ficticios', () => {
  const db = demoDb();
  assert.equal(seedDemoActivity(db, { enabled: false }), false);
  assert.equal(db.prepare('SELECT COUNT(*) n FROM users').get().n, 0);
  db.close();
});
