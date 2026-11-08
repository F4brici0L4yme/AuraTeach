export interface CanvasSceneNode {
  readonly nodePath: string;
  readonly name: string;
  readonly kind: 'mesh' | 'group';
}

export interface CanvasSceneSummary {
  readonly modelId: string | null;
  readonly viewId: 'current';
  readonly nodes: readonly CanvasSceneNode[];
}

export interface CanvasImagePointLocator {
  readonly kind: 'image-point';
  readonly viewId: TutorViewId | 'current';
  /** Normalized image coordinates, in the same mirrored orientation as the canvas view. */
  readonly uv: readonly [number, number];
}

export type TutorViewId = 'front' | 'back' | 'left' | 'right' | 'top';
export interface TutorSceneImage { readonly viewId: TutorViewId; readonly dataUrl: string; }
export const TUTOR_VIEW_PRESETS: readonly TutorViewId[] = ['front', 'back', 'left', 'right', 'top'];

export interface CanvasSemanticNodeLocator {
  readonly kind: 'semantic-node';
  readonly nodePath: string;
}

export type CanvasLocator = CanvasImagePointLocator | CanvasSemanticNodeLocator;

export interface CanvasSelection {
  readonly nodePath: string;
  readonly name: string;
  readonly kind: 'mesh' | 'group';
}

export type GuitarAssemblyState = 'assembled' | 'separated';

export interface CanvasAssemblyAction {
  readonly modelId: string;
  readonly partId: string;
  readonly state: GuitarAssemblyState;
}

/** Only curated, authored assembly actions are permitted by the canvas. */
export const CURATED_ASSEMBLY_MANIFEST = {
  modelId: 'guitarra-acustica',
  partId: 'tapa-armonica',
  nodeName: 'Tapa_armonica_desmontable',
  revealOffsetFraction: 0.42,
} as const;

export function validateCanvasLocator(locator: unknown, scene: CanvasSceneSummary): string | null {
  if (!locator || typeof locator !== 'object') return 'La ubicación del modelo no es válida.';
  const value = locator as Record<string, unknown>;
  if (value['kind'] === 'semantic-node') {
    return typeof value['nodePath'] === 'string' && scene.nodes.some((node) => node.nodePath === value['nodePath'])
      ? null
      : 'El tutor indicó una pieza que no está en el modelo actual.';
  }
  if (value['kind'] !== 'image-point') return 'El tipo de ubicación no está permitido.';
  if (value['viewId'] !== 'current' && !TUTOR_VIEW_PRESETS.includes(value['viewId'] as TutorViewId)) return 'La ubicación corresponde a otra vista del modelo.';
  const uv = value['uv'];
  if (!Array.isArray(uv) || uv.length !== 2 || !uv.every((coordinate) => typeof coordinate === 'number'
    && Number.isFinite(coordinate) && coordinate >= 0 && coordinate <= 1)) {
    return 'El punto de la imagen debe estar dentro del canvas.';
  }
  return null;
}

export function validateAssemblyAction(action: unknown, modelId: string | null): string | null {
  if (!action || typeof action !== 'object') return 'La acción de montaje no es válida.';
  const value = action as Record<string, unknown>;
  return modelId === CURATED_ASSEMBLY_MANIFEST.modelId
    && value['modelId'] === CURATED_ASSEMBLY_MANIFEST.modelId
    && value['partId'] === CURATED_ASSEMBLY_MANIFEST.partId
    && (value['state'] === 'assembled' || value['state'] === 'separated')
    ? null
    : 'Esta acción solo está disponible para la tapa armónica de la guitarra preparada.';
}
