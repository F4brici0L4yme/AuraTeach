import { CURATED_ASSEMBLY_MANIFEST, validateAssemblyAction, validateCanvasLocator, type CanvasSceneSummary } from './canvas-scene';

const scene: CanvasSceneSummary = {
  modelId: 'guitarra-acustica',
  viewId: 'current',
  nodes: [
    { nodePath: '/Scene/Guitarra[0]/Cuerpo[0]', name: 'Cuerpo', kind: 'mesh' },
    { nodePath: '/Scene/Guitarra[0]/Tapa_armonica_desmontable[1]', name: 'Tapa_armonica_desmontable', kind: 'mesh' },
  ],
};

describe('canvas locator validation', () => {
  it('accepts a semantic path present in the loaded model and rejects invented paths', () => {
    expect(validateCanvasLocator({ kind: 'semantic-node', nodePath: scene.nodes[1].nodePath }, scene)).toBeNull();
    expect(validateCanvasLocator({ kind: 'semantic-node', nodePath: '/Scene/InteriorInventado' }, scene)).toContain('no está');
  });

  it('accepts only points inside the current view and normalized image bounds', () => {
    expect(validateCanvasLocator({ kind: 'image-point', viewId: 'current', uv: [0.5, 0.5] }, scene)).toBeNull();
    expect(validateCanvasLocator({ kind: 'image-point', viewId: 'old', uv: [0.5, 0.5] }, scene)).toContain('otra vista');
    expect(validateCanvasLocator({ kind: 'image-point', viewId: 'current', uv: [1.1, 0.5] }, scene)).toContain('dentro');
    expect(validateCanvasLocator({ kind: 'image-point', viewId: 'current', uv: [0.2, Number.NaN] }, scene)).toContain('dentro');
    expect(validateCanvasLocator({ kind: 'world-position', xyz: { x: 1, y: 2, z: 3 } }, scene)).toContain('no está permitido');
  });
});

describe('curated guitar assembly action', () => {
  it('allows only the named guitar part in its two supported states', () => {
    expect(validateAssemblyAction({ modelId: 'guitarra-acustica', partId: 'tapa-armonica', state: 'separated' }, 'guitarra-acustica')).toBeNull();
    expect(validateAssemblyAction({ modelId: 'guitarra-acustica', partId: 'tapa-armonica', state: 'assembled' }, 'guitarra-acustica')).toBeNull();
    expect(validateAssemblyAction({ modelId: 'guitarra-acustica', partId: 'cuerdas', state: 'separated' }, 'guitarra-acustica')).toContain('solo está disponible');
    expect(validateAssemblyAction({ modelId: 'custom-upload', partId: 'tapa-armonica', state: 'separated' }, 'custom-upload')).toContain('solo está disponible');
    expect(CURATED_ASSEMBLY_MANIFEST.nodeName).toBe('Tapa_armonica_desmontable');
  });
});
