// Hand pose helpers kept independent from the camera and Three.js for testing.
export const isPreparedModel = model => Boolean(model && !model.own && model.id === 'lapicero' && model.disassemblable);

export function mapIndexToCanvas(point, rect) {
  if (!point || !rect?.width || !rect?.height) return null;
  return {
    // HandGestureState already mirrors x to match the mirrored camera preview.
    x: Math.max(0, Math.min(1, point.x)),
    y: Math.max(0, Math.min(1, point.y)),
  };
}

// A ratio greater than one means the hands moved apart. The resulting factor
// is applied to the camera's target offset: spreading the hands zooms in.
export function bimanualZoomFactor(previousSpread, currentSpread, sensitivity = 0.72) {
  if (!Number.isFinite(previousSpread) || !Number.isFinite(currentSpread)) return 1;
  const delta = Math.max(-0.35, Math.min(0.35, currentSpread - previousSpread));
  return Math.exp(-delta * sensitivity);
}

export class HandGestureState {
  constructor({
    pinchStart = 0.32,
    pinchEnd = 0.48,
    ringStart = 0.42,
    ringEnd = 0.59,
    smoothing = 0.38,
    poseConfirmMs = 120,
    modeHoldMs = 420,
    modeCooldownMs = 1000,
  } = {}) {
    Object.assign(this, { pinchStart, pinchEnd, ringStart, ringEnd, smoothing, poseConfirmMs, modeHoldMs, modeCooldownMs });
    this.reset();
  }

  reset() {
    this.pinch = false;
    this.ringPinch = false;
    this.ringStartedAt = null;
    this.modeToggleAt = -Infinity;
    this.modeToggleSent = false;
    this.point = null;
    this.pose = '';
    this.poseStartedAt = null;
  }

  update(landmarks, now = Date.now()) {
    if (!landmarks || landmarks.length < 21) {
      const pinchEnded = this.pinch;
      this.pinch = false;
      this.ringPinch = false;
      this.ringStartedAt = null;
      this.modeToggleSent = false;
      this.point = null;
      this.pose = '';
      this.poseStartedAt = null;
      return { visible: false, pinch: false, pinchStarted: false, pinchEnded, ringPinch: false, modeToggle: false, fist: false, pointing: false, point: null };
    }

    const d = (a, b) => Math.hypot(landmarks[a].x - landmarks[b].x, landmarks[a].y - landmarks[b].y);
    const palm = Math.max(0.025, d(0, 9));
    const pinchRatio = d(4, 8) / palm;
    const wasPinching = this.pinch;
    this.pinch = wasPinching ? pinchRatio < this.pinchEnd : pinchRatio < this.pinchStart;

    const ringRatio = d(4, 16) / palm;
    const wasRingPinching = this.ringPinch;
    this.ringPinch = wasRingPinching ? ringRatio < this.ringEnd : ringRatio < this.ringStart;
    if (this.ringPinch) {
      if (!wasRingPinching) this.ringStartedAt = now;
    } else {
      this.ringStartedAt = null;
      this.modeToggleSent = false;
    }
    const modeToggle = this.ringPinch && !this.modeToggleSent && this.ringStartedAt !== null
      && now - this.ringStartedAt >= this.modeHoldMs && now - this.modeToggleAt >= this.modeCooldownMs;
    if (modeToggle) {
      this.modeToggleSent = true;
      this.modeToggleAt = now;
    }

    const extended = ([tip, pip]) => d(0, tip) > d(0, pip) + palm * 0.12;
    const indexExtended = extended([8, 6]);
    const otherFingersFolded = [[12, 10], [16, 14], [20, 18]].every(([tip, pip]) => !extended([tip, pip]));
    const pointingCandidate = indexExtended && otherFingersFolded && !this.ringPinch;
    const fistCandidate = [[8, 6], [12, 10], [16, 14], [20, 18]].every(([tip, pip]) => !extended([tip, pip])) && !this.ringPinch;
    const nextPose = pointingCandidate ? 'pointing' : fistCandidate ? 'fist' : '';
    if (nextPose !== this.pose) {
      this.pose = nextPose;
      this.poseStartedAt = now;
    }
    const poseStable = Boolean(nextPose && this.poseStartedAt !== null && now - this.poseStartedAt >= this.poseConfirmMs);

    const raw = { x: 1 - landmarks[8].x, y: landmarks[8].y };
    this.point = this.point
      ? { x: this.point.x + (raw.x - this.point.x) * this.smoothing, y: this.point.y + (raw.y - this.point.y) * this.smoothing }
      : raw;
    return {
      visible: true,
      pinch: this.pinch,
      pinchStarted: !wasPinching && this.pinch,
      pinchEnded: wasPinching && !this.pinch,
      ringPinch: this.ringPinch,
      modeToggle,
      fist: poseStable && nextPose === 'fist',
      pointing: poseStable && nextPose === 'pointing',
      point: this.point,
      palm,
    };
  }
}
