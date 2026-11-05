import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

test('lapicero preparado tiene posiciones ensambladas y explotadas para sus 38 mallas', async () => {
  const manifest = JSON.parse(await readFile(path.join(root, 'demo-lapicero/lapicero-parts.json'), 'utf8'));
  assert.equal(manifest.modelId, 'lapicero');
  assert.equal(manifest.parts.length, 38);
  for (const part of manifest.parts) {
    assert.ok(part.nodeName);
    assert.equal(part.originPosition.length, 3);
    assert.equal(part.explodedPosition.length, 3);
    assert.ok([...part.originPosition, ...part.explodedPosition].every(Number.isFinite));
  }
  assert.notDeepEqual(
    manifest.parts.find(part => part.nodeName === 'Clip · curva').originPosition,
    manifest.parts.find(part => part.nodeName === 'Clip · curva').explodedPosition
  );
});
