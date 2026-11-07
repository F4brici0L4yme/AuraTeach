import { cameraScaleForRadius, validateCanvasCommand } from './canvas-command';

describe('canvas command contract', () => {
  it('accepts valid plain-data commands and rejects unsafe values', () => {
    expect(validateCanvasCommand({ type: 'camera.zoom', factor: 2 })).toBeNull();
    expect(validateCanvasCommand({ type: 'camera.focus', target: { kind: 'node', nodeName: 'Stem' } })).toBeNull();
    expect(validateCanvasCommand({ type: 'camera.zoom', factor: Number.POSITIVE_INFINITY })).toContain('zoom');
    expect(validateCanvasCommand({ type: 'camera.zoom', factor: 21 })).toContain('zoom');
    expect(validateCanvasCommand({ type: 'camera.focus', target: null })).toContain('objetivo');
    expect(validateCanvasCommand({ type: 'annotation.add', id: 'a1', label: 'Parte', origin: { x: 0, y: 0, z: 0 } }))
      .toContain('permitido');
    expect(validateCanvasCommand({ type: 'execute-javascript', source: 'alert(1)' })).toContain('permitido');
    expect(validateCanvasCommand(null)).toContain('comando');
  });

  it('derives zoom and clipping ranges from model scale', () => {
    const small = cameraScaleForRadius(0.01);
    const large = cameraScaleForRadius(1000);

    expect(small.minDistance).toBeCloseTo(0.00002);
    expect(large.minDistance).toBeCloseTo(2);
    expect(large.maxDistance / small.maxDistance).toBeCloseTo(100_000);
    expect(small.nearPlane).toBeGreaterThan(0);
    expect(large.farPlane).toBeGreaterThan(large.maxDistance);
  });

  it('uses a safe scale for zero or non-finite model radii', () => {
    expect(cameraScaleForRadius(0)).toEqual(cameraScaleForRadius(Number.NaN));
    expect(cameraScaleForRadius(Number.POSITIVE_INFINITY).nearPlane).toBeGreaterThan(0);
  });
});
