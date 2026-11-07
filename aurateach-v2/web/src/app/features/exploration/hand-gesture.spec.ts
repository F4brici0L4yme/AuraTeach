import { bimanualZoomFactor, HandGestureTracker } from './hand-gesture';

interface Landmark { x: number; y: number; z?: number }

function hand({ index = false, pinch = false } = {}): Landmark[] {
  const points: Landmark[] = Array.from({ length: 21 }, () => ({ x: 0.5, y: 0.65 }));
  points[0] = { x: 0.5, y: 0.82 };
  points[9] = { x: 0.5, y: 0.52 };
  for (const [mcp, pip, tip, x] of [[5, 6, 8, 0.37], [9, 10, 12, 0.45], [13, 14, 16, 0.55], [17, 18, 20, 0.63]]) {
    points[mcp] = { x, y: 0.52 };
    points[pip] = { x, y: 0.62 };
    points[tip] = { x, y: 0.66 };
  }
  points[6] = { x: 0.37, y: 0.42 };
  points[8] = index ? { x: 0.37, y: 0.25 } : { x: 0.37, y: 0.66 };
  points[4] = pinch ? { x: points[8].x + 0.015, y: points[8].y } : { x: 0.24, y: 0.63 };
  return points;
}

describe('hand gesture interaction mapping', () => {
  it('orbits only after a fist is stable and returns smoothed movement deltas', () => {
    const tracker = new HandGestureTracker({ poseConfirmMs: 100, smoothing: 1 });
    expect(tracker.update([hand()], 0).orbit).toBeNull();
    expect(tracker.update([hand()], 100).orbit).toBeNull();
    const moved = hand();
    for (const p of moved) p.x -= 0.1;
    expect(Math.abs(tracker.update([moved], 120).orbit?.azimuthRadians ?? 0)).toBeGreaterThan(0);
  });

  it('maps index pointing to a mirrored normalized reticle and reports pinch edge', () => {
    const tracker = new HandGestureTracker({ poseConfirmMs: 0, smoothing: 1 });
    const pointed = hand({ index: true });
    const pointing = tracker.update([pointed], 0);
    expect(pointing.reticle).toEqual({ x: 0.63, y: 0.25 });
    expect(pointing.selected).toBe(false);
    const pinched = tracker.update([hand({ index: true, pinch: true })], 20);
    expect(pinched.selected).toBe(true);
    expect(tracker.update([hand({ index: true, pinch: true })], 40).selected).toBe(false);
  });

  it('zooms from two-hand spread changes and clamps large jumps', () => {
    expect(bimanualZoomFactor(0.3, 0.5)).toBeGreaterThan(1);
    expect(bimanualZoomFactor(0.5, 0.3)).toBeLessThan(1);
    expect(bimanualZoomFactor(0.5, 0.5)).toBe(1);
    expect(bimanualZoomFactor(0, 1)).toBeLessThan(1.22);
    const tracker = new HandGestureTracker();
    const left = hand();
    const right = hand();
    for (const point of left) point.x -= 0.2;
    for (const point of right) point.x += 0.2;
    expect(tracker.update([left, right], 0).zoomFactor).toBe(1);
    for (const point of left) point.x -= 0.08;
    for (const point of right) point.x += 0.08;
    expect(tracker.update([left, right], 40).zoomFactor).toBeGreaterThan(1);
  });

  it('clears reticle and pose when tracking is lost', () => {
    const tracker = new HandGestureTracker({ poseConfirmMs: 0 });
    tracker.update([hand({ index: true })], 0);
    const lost = tracker.update([], 20);
    expect(lost.reticle).toBeNull();
    expect(lost.orbit).toBeNull();
    expect(lost.visibleHands).toBe(0);
  });
});
