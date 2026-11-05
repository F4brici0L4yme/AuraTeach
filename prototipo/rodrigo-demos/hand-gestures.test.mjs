import test from 'node:test';
import assert from 'node:assert/strict';
import { HandGestureState, isPreparedModel, mapIndexToCanvas, bimanualZoomFactor } from './hand-gestures.mjs';

function hand({ index = 'folded', thumb = 'away', ring = 'folded' } = {}) {
  const points = Array.from({ length: 21 }, () => ({ x: 0.5, y: 0.65 }));
  points[0] = { x: 0.5, y: 0.8 };
  points[9] = { x: 0.5, y: 0.5 };
  for (const [mcp, pip, tip, x] of [[5, 6, 8, 0.37], [9, 10, 12, 0.45], [13, 14, 16, 0.55], [17, 18, 20, 0.63]]) {
    points[mcp] = { x, y: 0.52 };
    points[pip] = { x, y: 0.62 };
    points[tip] = { x, y: 0.66 };
  }
  points[6] = { x: 0.37, y: 0.42 };
  points[8] = index === 'extended' ? { x: 0.37, y: 0.25 } : { x: 0.37, y: 0.66 };
  points[4] = thumb === 'ring' ? { ...points[16] } : thumb === 'index' ? { ...points[8] } : { x: 0.25, y: 0.63 };
  return points;
}

test('pinch uses separate press/release thresholds and reports the rising edge', () => {
  const g = new HandGestureState();
  let lm = hand({ index: 'extended', thumb: 'index' });
  assert.equal(g.update(lm, 0).pinchStarted, true);
  lm[4] = { x: lm[8].x + 0.06, y: lm[8].y };
  assert.equal(g.update(lm, 30).pinch, true, 'pinch remains active inside hysteresis');
  lm[4] = { x: lm[8].x + 0.18, y: lm[8].y };
  assert.equal(g.update(lm, 60).pinchEnded, true);
});

test('fist and pointing poses require a short stable confirmation', () => {
  const g = new HandGestureState();
  const fist = hand();
  assert.equal(g.update(fist, 0).fist, false);
  assert.equal(g.update(fist, 119).fist, false);
  assert.equal(g.update(fist, 120).fist, true);
  const point = hand({ index: 'extended' });
  assert.equal(g.update(point, 200).pointing, false);
  assert.equal(g.update(point, 320).pointing, true);
});

test('thumb plus ring toggles once after hold and respects cooldown', () => {
  const g = new HandGestureState({ modeHoldMs: 400, modeCooldownMs: 900 });
  const ring = hand({ thumb: 'ring' });
  assert.equal(g.update(ring, 0).modeToggle, false);
  assert.equal(g.update(ring, 399).modeToggle, false);
  assert.equal(g.update(ring, 400).modeToggle, true);
  assert.equal(g.update(ring, 600).modeToggle, false, 'holding cannot repeatedly toggle');
  g.update(hand(), 700);
  g.update(ring, 800);
  assert.equal(g.update(ring, 1200).modeToggle, false, 'cooldown suppresses a quick second toggle');
  assert.equal(g.update(ring, 1700).modeToggle, true, 'toggle is available after cooldown');
});

test('lost tracking releases pinch and resets pose', () => {
  const g = new HandGestureState();
  g.update(hand({ index: 'extended', thumb: 'index' }), 0);
  const missing = g.update([], 20);
  assert.equal(missing.visible, false);
  assert.equal(missing.pinchEnded, true);
  assert.equal(missing.point, null);
});

test('canvas mapping retains mirrored preview coordinates and clamps to viewport', () => {
  assert.deepEqual(mapIndexToCanvas({ x: 0.2, y: 0.7 }, { width: 800, height: 600 }), { x: 0.2, y: 0.7 });
  assert.deepEqual(mapIndexToCanvas({ x: 1.2, y: -0.2 }, { width: 800, height: 600 }), { x: 1, y: 0 });
  assert.equal(mapIndexToCanvas({ x: 0, y: 0 }, { width: 0, height: 10 }), null);
});

test('moving hands apart zooms in and moving them together zooms out', () => {
  assert.ok(bimanualZoomFactor(1, 1.1) < 1);
  assert.ok(bimanualZoomFactor(1.1, 1) > 1);
  assert.equal(bimanualZoomFactor(1, 1), 1);
});

test('decomposition is enabled only for the prepared school pen, never a user GLB', () => {
  assert.equal(isPreparedModel({ id: 'lapicero', disassemblable: true, own: false }), true);
  assert.equal(isPreparedModel({ id: 'lapicero', disassemblable: true, own: true }), false);
  assert.equal(isPreparedModel({ id: 'maceta', disassemblable: true, own: false }), false);
  assert.equal(isPreparedModel({ id: 'lapicero', disassemblable: false, own: false }), false);
});
