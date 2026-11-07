/** MediaPipe landmark-shaped data kept independent from Three.js and camera APIs. */
export interface HandLandmark { readonly x: number; readonly y: number; readonly z?: number; }

export interface HandGestureOutput {
  readonly visibleHands: number;
  readonly orbit: { readonly azimuthRadians: number; readonly polarRadians: number } | null;
  /** A factor above 1 moves the camera closer when hands spread apart. */
  readonly zoomFactor: number;
  readonly reticle: { readonly x: number; readonly y: number } | null;
  /** True only on the pinch rising edge while the index is pointing. */
  readonly selected: boolean;
}

export interface HandGestureOptions {
  readonly poseConfirmMs?: number;
  readonly smoothing?: number;
  readonly pinchStartRatio?: number;
  readonly pinchReleaseRatio?: number;
  readonly orbitSensitivity?: number;
  readonly zoomSensitivity?: number;
  readonly motionDeadZone?: number;
}

/** Converts two-hand landmark streams into plain canvas intents. */
export class HandGestureTracker {
  private readonly poseConfirmMs: number;
  private readonly smoothing: number;
  private readonly pinchStartRatio: number;
  private readonly pinchReleaseRatio: number;
  private readonly orbitSensitivity: number;
  private readonly zoomSensitivity: number;
  private readonly motionDeadZone: number;
  private pose: 'fist' | 'pointing' | '' = '';
  private poseSince = 0;
  private pinch = false;
  private previousCenter: { x: number; y: number } | null = null;
  private smoothedCenter: { x: number; y: number } | null = null;
  private previousSpread: number | null = null;

  constructor(options: HandGestureOptions = {}) {
    this.poseConfirmMs = options.poseConfirmMs ?? 120;
    this.smoothing = options.smoothing ?? 0.38;
    this.pinchStartRatio = options.pinchStartRatio ?? 0.32;
    this.pinchReleaseRatio = options.pinchReleaseRatio ?? 0.48;
    this.orbitSensitivity = options.orbitSensitivity ?? 3.5;
    this.zoomSensitivity = options.zoomSensitivity ?? 2.4;
    this.motionDeadZone = options.motionDeadZone ?? 0.003;
  }

  update(hands: readonly (readonly HandLandmark[])[], now = Date.now()): HandGestureOutput {
    const valid = hands.filter((landmarks) => landmarks.length >= 21).slice(0, 2);
    const first = valid[0];
    if (!first) {
      this.reset();
      return { visibleHands: 0, orbit: null, zoomFactor: 1, reticle: null, selected: false };
    }

    const center = palmCenter(first);
    this.smoothedCenter = this.smoothedCenter
      ? {
          x: this.smoothedCenter.x + (center.x - this.smoothedCenter.x) * this.smoothing,
          y: this.smoothedCenter.y + (center.y - this.smoothedCenter.y) * this.smoothing,
        }
      : center;
    const rawPoint = { x: clamp(1 - first[8].x), y: clamp(first[8].y) };
    const pose = classifyPose(first);
    if (pose !== this.pose) {
      this.pose = pose;
      this.poseSince = now;
      this.previousCenter = this.smoothedCenter;
    }
    const stable = pose !== '' && now - this.poseSince >= this.poseConfirmMs;

    let orbit: HandGestureOutput['orbit'] = null;
    if (stable && pose === 'fist' && this.previousCenter && this.smoothedCenter) {
      const dx = this.smoothedCenter.x - this.previousCenter.x;
      const dy = this.smoothedCenter.y - this.previousCenter.y;
      if (Math.abs(dx) >= this.motionDeadZone || Math.abs(dy) >= this.motionDeadZone) {
        orbit = { azimuthRadians: dx * this.orbitSensitivity, polarRadians: dy * this.orbitSensitivity };
      }
    }
    this.previousCenter = this.smoothedCenter;

    const pinching = pinchRatio(first) < (this.pinch ? this.pinchReleaseRatio : this.pinchStartRatio);
    const selected = stable && pose === 'pointing' && pinching && !this.pinch;
    this.pinch = pinching;

    let zoomFactor = 1;
    if (valid.length === 2) {
      const spread = distance(palmCenter(valid[0]), palmCenter(valid[1]));
      if (this.previousSpread !== null) zoomFactor = bimanualZoomFactor(this.previousSpread, spread, this.zoomSensitivity);
      this.previousSpread = spread;
    } else {
      this.previousSpread = null;
    }
    return {
      visibleHands: valid.length,
      orbit,
      zoomFactor,
      reticle: stable && pose === 'pointing' ? rawPoint : null,
      selected,
    };
  }

  reset(): void {
    this.pose = '';
    this.poseSince = 0;
    this.pinch = false;
    this.previousCenter = null;
    this.smoothedCenter = null;
    this.previousSpread = null;
  }
}

export function bimanualZoomFactor(previousSpread: number, currentSpread: number, sensitivity = 2.4): number {
  if (![previousSpread, currentSpread, sensitivity].every(Number.isFinite)) return 1;
  const spreadDelta = clamp(currentSpread - previousSpread, -0.08, 0.08);
  if (Math.abs(spreadDelta) < 0.006) return 1;
  return Math.exp(spreadDelta * sensitivity);
}

function classifyPose(points: readonly HandLandmark[]): 'fist' | 'pointing' | '' {
  const wrist = points[0];
  const palm = Math.max(distance(wrist, points[9]), 0.025);
  const indexExtended = distance(wrist, points[8]) > distance(wrist, points[6]) + palm * 0.12;
  const otherFingersFolded = [[12, 10], [16, 14], [20, 18]].every(([tip, pip]) =>
    distance(wrist, points[tip]) <= distance(wrist, points[pip]) + palm * 0.12,
  );
  if (indexExtended && otherFingersFolded) return 'pointing';
  const fourFolded = [[8, 6], [12, 10], [16, 14], [20, 18]].every(([tip, pip]) =>
    distance(wrist, points[tip]) <= distance(wrist, points[pip]) + palm * 0.12,
  );
  return fourFolded ? 'fist' : '';
}

function palmCenter(points: readonly HandLandmark[]): { x: number; y: number } {
  return { x: (points[0].x + points[5].x + points[9].x + points[13].x + points[17].x) / 5,
    y: (points[0].y + points[5].y + points[9].y + points[13].y + points[17].y) / 5 };
}

function pinchRatio(points: readonly HandLandmark[]): number {
  return distance(points[4], points[8]) / Math.max(distance(points[0], points[9]), 0.025);
}

function distance(a: HandLandmark, b: HandLandmark): number { return Math.hypot(a.x - b.x, a.y - b.y); }
function clamp(value: number, min = 0, max = 1): number { return Math.max(min, Math.min(max, value)); }
