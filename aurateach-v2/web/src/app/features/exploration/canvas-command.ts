/** Plain-data commands accepted by the exploration canvas. No Three.js types cross this boundary. */
export type CanvasCommand =
  | { readonly type: 'camera.reset' }
  | { readonly type: 'camera.zoom'; readonly factor: number }
  | {
      readonly type: 'camera.orbit';
      readonly azimuthRadians: number;
      readonly polarRadians: number;
    }
  | {
      readonly type: 'camera.preset';
      readonly preset: 'front' | 'back' | 'left' | 'right' | 'top';
    }
  | {
      readonly type: 'camera.focus';
      readonly target: { readonly kind: 'model' } | { readonly kind: 'node'; readonly nodeName: string };
    }
  | { readonly type: 'model.highlight'; readonly nodeName: string; readonly active: boolean }
  | { readonly type: 'annotation.clear'; readonly id?: string };

/** Coordinates used only for anchors created internally after a canvas raycast. */
export interface CanvasVector3 {
  readonly x: number;
  readonly y: number;
  readonly z: number;
}

export type CanvasLifecycleState = 'loading' | 'ready' | 'failed' | 'destroyed';

export type CanvasCommandResult =
  | { readonly status: 'applied' }
  | { readonly status: 'not-ready'; readonly state: Exclude<CanvasLifecycleState, 'ready'> }
  | { readonly status: 'invalid-command'; readonly reason: string }
  | { readonly status: 'unsupported-target'; readonly target: string; readonly reason: string };

export type CanvasReadyResult = 'ready' | 'failed' | 'destroyed';

/**
 * Inbound port for any input adapter (voice, gestures, UI, or tutor tools) controlling the canvas.
 * Implementations may use Three.js internally, but callers only exchange serializable data.
 */
export interface CanvasCommandPort {
  readonly lifecycleState: CanvasLifecycleState;
  execute(command: CanvasCommand): CanvasCommandResult;
  waitUntilReady(): Promise<CanvasReadyResult>;
}

export interface CameraScale {
  readonly minDistance: number;
  readonly maxDistance: number;
  readonly nearPlane: number;
  readonly farPlane: number;
}

/** Derives camera clipping and orbit limits from the radius of the current model or focus target. */
export function cameraScaleForRadius(radius: number): CameraScale {
  const safeRadius = Number.isFinite(radius) ? Math.max(Math.abs(radius), 0.0001) : 0.0001;
  const minDistance = Math.max(safeRadius * 0.002, safeRadius * 0.0002);
  return {
    minDistance,
    maxDistance: Math.max(safeRadius * 100, minDistance * 1000),
    nearPlane: Math.max(safeRadius * 0.0001, 0.000001),
    farPlane: safeRadius * 1000,
  };
}

/** Runtime validation is required because future voice/tutor adapters may provide untrusted JSON. */
export function validateCanvasCommand(input: unknown): string | null {
  if (!input || typeof input !== 'object' || !('type' in input)) return 'El comando no es válido.';
  const command = input as Record<string, unknown>;
  switch (command['type']) {
    case 'camera.reset':
      return null;
    case 'camera.zoom':
      return typeof command['factor'] === 'number' && Number.isFinite(command['factor'])
        && command['factor'] >= 0.05 && command['factor'] <= 20
        ? null
        : 'El zoom debe ser un factor entre 0.05 y 20.';
    case 'camera.orbit':
      return typeof command['azimuthRadians'] === 'number' && Number.isFinite(command['azimuthRadians'])
        && typeof command['polarRadians'] === 'number' && Number.isFinite(command['polarRadians'])
        && Math.abs(command['azimuthRadians']) <= Math.PI * 4 && Math.abs(command['polarRadians']) <= Math.PI * 4
        ? null
        : 'La órbita debe usar radianes finitos dentro del rango permitido.';
    case 'camera.preset':
      return ['front', 'back', 'left', 'right', 'top'].includes(String(command['preset']))
        ? null
        : 'La vista solicitada no existe.';
    case 'camera.focus': {
      const target = command['target'];
      if (!target || typeof target !== 'object' || !('kind' in target)) return 'El objetivo de enfoque no es válido.';
      const focusTarget = target as Record<string, unknown>;
      return focusTarget['kind'] === 'model'
        ? null
        : focusTarget['kind'] === 'node' && validText(focusTarget['nodeName'], 1, 120)
          ? null
          : 'El objetivo de enfoque no es válido.';
    }
    case 'model.highlight':
      return validText(command['nodeName'], 1, 120) && typeof command['active'] === 'boolean'
        ? null
        : 'La selección de resaltado no es válida.';
    case 'annotation.clear':
      return command['id'] === undefined || validText(command['id'], 1, 80)
        ? null
        : 'El identificador de anotación no es válido.';
    default:
      return 'El tipo de comando no está permitido.';
  }
}

function validText(value: unknown, minimum: number, maximum: number): value is string {
  return typeof value === 'string' && value.trim().length >= minimum && value.length <= maximum;
}
