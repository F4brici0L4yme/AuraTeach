import { Component, ElementRef, OnDestroy, afterNextRender, input, output, signal, viewChild } from '@angular/core';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { TransformControls } from 'three/addons/controls/TransformControls.js';
import type {
  CanvasCommand,
  CanvasCommandPort,
  CanvasCommandResult,
  CanvasLifecycleState,
  CanvasReadyResult,
} from './canvas-command';
import { cameraScaleForRadius, validateCanvasCommand } from './canvas-command';
import {
  CURATED_ASSEMBLY_MANIFEST,
  validateAssemblyAction,
  validateCanvasLocator,
  type CanvasAssemblyAction,
  type CanvasLocator,
  type CanvasSceneNode,
  type CanvasSceneSummary,
  type CanvasSelection,
  type GuitarAssemblyState,
  type TutorSceneImage,
  type TutorViewId,
  TUTOR_VIEW_PRESETS,
} from './canvas-scene';
import { HandGestureTracker, type HandLandmark } from './hand-gesture';

interface MediaPipeHandTask {
  detectForVideo(video: HTMLVideoElement, timestamp: number): { readonly landmarks?: readonly (readonly HandLandmark[])[] };
  close(): void;
}

interface MediaPipeVisionModule {
  readonly FilesetResolver: {
    forVisionTasks(wasmPath: string): Promise<unknown>;
  };
  readonly HandLandmarker: {
    createFromOptions(files: unknown, options: Record<string, unknown>): Promise<MediaPipeHandTask>;
  };
}

@Component({
  selector: 'app-glb-viewport',
  template: `
    <section class="viewer" aria-label="Visor 3D del modelo">
      <canvas #canvas aria-label="Modelo tridimensional. Arrastra para rotar y usa la rueda para acercar."></canvas>
      <video #handVideo class="hand-video" muted playsinline aria-hidden="true"></video>
      @if (loading()) { <div class="viewer-message" role="status">Cargando modelo 3D…</div> }
      @if (error()) { <div class="viewer-message viewer-error" role="alert">{{ error() }}</div> }
      <div class="hand-tools">
        <button type="button" class="hand-button" (click)="toggleHands()" [disabled]="loading() || !!error()">
          {{ handsEnabled() ? 'Detener manos' : 'Manos' }}
        </button>
        @if (handsStatus()) { <span class="hand-status" role="status" aria-live="polite">{{ handsStatus() }}</span> }
      </div>
      @if (reticle(); as point) {
        <div class="hand-reticle" aria-hidden="true" [style.left.%]="point.x * 100" [style.top.%]="point.y * 100"></div>
      }
      @if (selection(); as selected) {
        <div class="selection-label" role="status" aria-live="polite">Pieza señalada: {{ selected.name }}</div>
      }
      @if (modelId() === 'guitarra-acustica' && lifecycleState === 'ready') {
        <button type="button" class="assembly-button" (click)="toggleGuitarAssembly()">
          {{ guitarState() === 'assembled' ? 'Separar tapa armónica' : 'Volver a montar guitarra' }}
        </button>
      }
      <div class="viewer-help">Arrastra para rotar · Rueda para zoom · Clic en una pieza y mueve sus flechas XYZ</div>
    </section>
  `,
  styles: `
    :host { display: block; width: 100%; height: 100%; min-width: 0; min-height: 0; }
    .viewer { position: relative; width: 100%; height: 100%; min-height: 0; overflow: hidden; background: #fff; }
    canvas { width: 100%; height: 100%; display: block; touch-action: none; }
    .viewer-message { position: absolute; inset: 0; display: grid; place-items: center; background: #fffffff0; color: #526078; }
    .viewer-error { color: #9b1c1c; }
    .viewer-help { position: absolute; left: 190px; bottom: 14px; padding: 8px 12px; border-radius: 999px; background: #ffffffdc; color: #526078; font-size: 13px; pointer-events: none; }
    .hand-tools { position: absolute; top: 14px; right: 14px; z-index: 2; display: flex; align-items: center; gap: 8px; max-width: min(480px, calc(100% - 28px)); }
    .hand-button, .assembly-button { border: 1px solid #d5dcea; border-radius: 999px; padding: 9px 14px; background: #fff; color: #24365d; font: inherit; font-weight: 650; box-shadow: 0 4px 16px #20304a18; cursor: pointer; }
    .hand-button:disabled { opacity: .55; cursor: not-allowed; }
    .hand-status { max-width: 320px; padding: 7px 10px; border-radius: 10px; background: #ffffffed; color: #526078; font-size: 12px; box-shadow: 0 4px 16px #20304a18; }
    .hand-video { position: absolute; top: 0; left: 0; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
    .hand-reticle { position: absolute; z-index: 2; width: 24px; height: 24px; border: 2px solid #3e64b5; border-radius: 50%; transform: translate(-50%, -50%); box-shadow: 0 0 0 4px #fff9, 0 2px 10px #1a2e5544; pointer-events: none; }
    .selection-label { position: absolute; z-index: 2; left: 50%; top: 14px; transform: translateX(-50%); max-width: min(420px, calc(100% - 200px)); padding: 7px 11px; border: 1px solid #cbd8f2; border-radius: 9px; background: #fff; color: #27313f; font-size: 13px; box-shadow: 0 4px 16px #20304a18; pointer-events: none; }
    .assembly-button { position: absolute; left: 14px; bottom: 14px; z-index: 2; }
    @media (max-width: 560px) { .hand-tools { top: 10px; right: 10px; } .hand-status { max-width: 210px; } .assembly-button { left: 10px; bottom: 10px; } .viewer-help { left: 10px; bottom: 62px; } }
  `,
})
export class GlbViewport implements OnDestroy, CanvasCommandPort {
  readonly src = input.required<string>();
  readonly modelId = input<string | null>(null);
  readonly selectionChanged = output<CanvasSelection | null>();

  private readonly canvasRef = viewChild<ElementRef<HTMLCanvasElement>>('canvas');
  private readonly handVideoRef = viewChild<ElementRef<HTMLVideoElement>>('handVideo');
  private readonly raycaster = new THREE.Raycaster();
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly handsEnabled = signal(false);
  protected readonly handsStatus = signal('');
  protected readonly reticle = signal<{ readonly x: number; readonly y: number } | null>(null);
  protected readonly selection = signal<CanvasSelection | null>(null);
  protected readonly guitarState = signal<GuitarAssemblyState>('assembled');
  private readonly scene = new THREE.Scene();
  private readonly loader = new GLTFLoader();
  private renderer?: THREE.WebGLRenderer;
  private camera?: THREE.PerspectiveCamera;
  private controls?: OrbitControls;
  private transformControls?: TransformControls;
  private transformHelper?: THREE.Object3D;
  private model?: THREE.Object3D;
  private resizeObserver?: ResizeObserver;
  private animationFrame = 0;
  private destroyed = false;
  private modelRadius = 1;
  private lifecycle: CanvasLifecycleState = 'loading';
  private settledReadiness = false;
  private resolveReadiness!: (result: CanvasReadyResult) => void;
  private readonly readiness = new Promise<CanvasReadyResult>((resolve) => {
    this.resolveReadiness = resolve;
  });
  private readonly highlighted = new Map<THREE.Mesh, {
    original: THREE.Material | THREE.Material[];
    replacement: THREE.Material | THREE.Material[];
  }>();
  private readonly annotations = new Map<string, THREE.Group>();
  private readonly handTracker = new HandGestureTracker();
  private handStream?: MediaStream;
  private handTask?: MediaPipeHandTask;
  private handAnimationFrame = 0;
  private handRequestId = 0;
  private hoveredMesh?: THREE.Mesh;
  private readonly assemblyOriginal = new Map<THREE.Object3D, { position: THREE.Vector3; quaternion: THREE.Quaternion; scale: THREE.Vector3 }>();
  private readonly sceneNodePaths = new Map<THREE.Object3D, string>();
  private lastRayHit: { readonly point: THREE.Vector3; readonly normal: THREE.Vector3 } | null = null;
  private cameraTransition: {
    readonly startedAt: number;
    readonly durationMs: number;
    readonly fromPosition: THREE.Vector3;
    readonly toPosition: THREE.Vector3;
    readonly fromTarget: THREE.Vector3;
    readonly toTarget: THREE.Vector3;
  } | null = null;
  private transformInteraction = false;
  private ignoreClickUntil = 0;
  private readonly canvasClickHandler = (event: MouseEvent): void => {
    if (event.button !== 0 || this.transformInteraction || performance.now() < this.ignoreClickUntil || !this.camera) return;
    const canvas = this.canvasRef()?.nativeElement;
    if (!canvas) return;
    const bounds = canvas.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const mesh = this.raycastAt((event.clientX - bounds.left) / bounds.width, (event.clientY - bounds.top) / bounds.height);
    if (mesh) this.selectMesh(mesh);
    else {
      this.selection.set(null);
      this.selectionChanged.emit(null);
      this.transformControls?.detach();
    }
  };

  constructor() {
    afterNextRender(() => this.initialize());
  }

  get lifecycleState(): CanvasLifecycleState {
    return this.lifecycle;
  }

  waitUntilReady(): Promise<CanvasReadyResult> {
    return this.readiness;
  }

  execute(command: CanvasCommand): CanvasCommandResult {
    const invalidReason = validateCanvasCommand(command);
    if (invalidReason) return { status: 'invalid-command', reason: invalidReason };
    if (this.lifecycle !== 'ready') return this.notReadyResult();

    switch (command.type) {
      case 'camera.reset':
        if (!this.model) return { status: 'not-ready', state: 'loading' };
        this.fitCamera(this.model);
        return { status: 'applied' };
      case 'camera.zoom':
        return this.zoom(command.factor);
      case 'camera.orbit':
        return this.orbit(command.azimuthRadians, command.polarRadians);
      case 'camera.preset':
        return this.setPreset(command.preset);
      case 'camera.focus':
        return this.focus(command.target);
      case 'model.highlight':
        return this.setHighlight(command.nodeName, command.active);
      case 'annotation.clear':
        return this.clearAnnotations(command.id);
    }
  }

  /** Plain scene index for tutor context; positions and Three.js objects never cross this boundary. */
  getSceneSummary(): CanvasSceneSummary {
    const nodes: CanvasSceneNode[] = [];
    this.sceneNodePaths.clear();
    if (this.model) this.model.traverse((node) => {
      if (this.isAnnotationNode(node)) return;
      const path = this.nodePath(node);
      this.sceneNodePaths.set(node, path);
      if (node === this.model) return;
      const mesh = (node as THREE.Mesh).isMesh;
      nodes.push({ nodePath: path, name: node.name || (mesh ? 'Malla sin nombre' : 'Grupo'), kind: mesh ? 'mesh' : 'group' });
    });
    return { modelId: this.modelId(), viewId: 'current', nodes: nodes.slice(0, 500) };
  }

  /** Captures the current visible canvas as a bounded JPEG data URL for an explicit tutor question. */
  captureSceneFrame(): string | null {
    if (!this.renderer || !this.camera || this.lifecycle !== 'ready') return null;
    try {
      this.renderer.render(this.scene, this.camera);
      const source = this.renderer.domElement;
      const scale = Math.min(1, 1100 / Math.max(source.width, source.height));
      const image = document.createElement('canvas');
      image.width = Math.max(1, Math.round(source.width * scale));
      image.height = Math.max(1, Math.round(source.height * scale));
      const context = image.getContext('2d');
      if (!context) return null;
      context.drawImage(source, 0, 0, image.width, image.height);
      return image.toDataURL('image/jpeg', 0.72);
    } catch {
      return null;
    }
  }

  /** Renders five fixed viewpoints locally; only these compressed JPEGs may leave the browser. */
  captureSceneViews(): TutorSceneImage[] {
    if (!this.renderer || !this.camera || !this.controls || this.lifecycle !== 'ready') return [];
    const originalPosition = this.camera.position.clone();
    const originalUp = this.camera.up.clone();
    const originalTarget = this.controls.target.clone();
    const originalTransition = this.cameraTransition;
    const originalHover = this.hoveredMesh;
    const helperVisible = this.transformHelper?.visible ?? false;
    const annotationVisibility = [...this.annotations.values()].map((annotation) => [annotation, annotation.visible] as const);
    const images: TutorSceneImage[] = [];
    this.cameraTransition = null;
    this.setHover(undefined);
    if (this.transformHelper) this.transformHelper.visible = false;
    for (const [annotation] of annotationVisibility) annotation.visible = false;
    try {
      for (const viewId of TUTOR_VIEW_PRESETS) {
        this.setPreset(viewId);
        this.renderer.render(this.scene, this.camera);
        const source = this.renderer.domElement;
        const scale = Math.min(1, 600 / Math.max(source.width, source.height));
        const image = document.createElement('canvas');
        image.width = Math.max(1, Math.round(source.width * scale));
        image.height = Math.max(1, Math.round(source.height * scale));
        const context = image.getContext('2d');
        if (!context) return [];
        context.drawImage(source, 0, 0, image.width, image.height);
        images.push({ viewId, dataUrl: image.toDataURL('image/jpeg', 0.55) });
      }
      return images;
    } catch {
      return [];
    } finally {
      this.camera.position.copy(originalPosition);
      this.camera.up.copy(originalUp);
      this.controls.target.copy(originalTarget);
      this.controls.update();
      this.cameraTransition = originalTransition;
      if (this.transformHelper) this.transformHelper.visible = helperVisible;
      for (const [annotation, visible] of annotationVisibility) annotation.visible = visible;
      if (originalHover) this.setHover(originalHover);
      this.renderer.render(this.scene, this.camera);
    }
  }

  /** Validates a tutor locator and resolves it against this scene before creating an anchored arrow. */
  applyLocator(locator: CanvasLocator, label: string): CanvasCommandResult {
    if (this.lifecycle !== 'ready' || !this.model || !this.camera) return this.notReadyResult();
    if (typeof label !== 'string' || !label.trim() || label.length > 120) {
      return { status: 'invalid-command', reason: 'La etiqueta de la señal debe tener entre 1 y 120 caracteres.' };
    }
    const summary = this.getSceneSummary();
    const invalid = validateCanvasLocator(locator, summary);
    if (invalid) return { status: 'invalid-command', reason: invalid };
    if (locator.kind === 'image-point' && locator.viewId !== 'current') this.setPreset(locator.viewId as TutorViewId);
    const target = locator.kind === 'semantic-node'
      ? this.sceneNodePathsTarget(locator.nodePath)
      : this.raycastAt(locator.uv[0], locator.uv[1]);
    if (!target) return { status: 'unsupported-target', target: locator.kind, reason: 'No se encontró una pieza visible en ese punto.' };
    const mesh = (target as THREE.Mesh).isMesh ? target as THREE.Mesh : this.firstMesh(target);
    if (!mesh) return { status: 'unsupported-target', target: locator.kind, reason: 'La pieza no contiene una superficie visible.' };
    const surface = locator.kind === 'image-point'
      ? this.lastRayHit
      : this.surfacePointFacingCamera(mesh);
    if (!surface) return { status: 'unsupported-target', target: locator.kind, reason: 'No se encontró una superficie visible en la pieza señalada.' };
    const origin = surface.point.clone();
    this.focusObject(mesh);
    this.addAnchoredAnnotation(mesh, origin, label);
    return { status: 'applied' };
  }

  /** Selected item from a hand pinch or pointer click, exposed as plain data. */
  selectionStatus(): CanvasSelection | null { return this.selection(); }

  /** Maps normalized canvas coordinates to a real visible mesh using an internal raycast. */
  selectAt(point: { readonly x: number; readonly y: number }): CanvasSelection | null {
    const mesh = this.raycastAt(point.x, point.y);
    if (!mesh) return null;
    return this.selectMesh(mesh);
  }

  private selectMesh(mesh: THREE.Mesh): CanvasSelection {
    const item = this.selectionFor(mesh);
    this.selection.set(item);
    this.selectionChanged.emit(item);
    this.setHover(mesh);
    this.transformControls?.attach(mesh);
    return item;
  }

  /** Applies the single authored guitar assembly operation; no arbitrary transforms are accepted. */
  applyAssemblyAction(action: CanvasAssemblyAction): CanvasCommandResult {
    const invalid = validateAssemblyAction(action, this.modelId());
    if (invalid) return { status: 'invalid-command', reason: invalid };
    if (this.lifecycle !== 'ready' || !this.model) return this.notReadyResult();
    const matches: THREE.Object3D[] = [];
    this.model.traverse((node) => { if (node.name === CURATED_ASSEMBLY_MANIFEST.nodeName) matches.push(node); });
    if (matches.length !== 1) return { status: 'unsupported-target', target: action.partId, reason: 'La tapa armónica no está identificada de forma única en este GLB.' };
    const part = matches[0];
    if (!this.assemblyOriginal.has(part)) this.assemblyOriginal.set(part, { position: part.position.clone(), quaternion: part.quaternion.clone(), scale: part.scale.clone() });
    const original = this.assemblyOriginal.get(part)!;
    if (action.state === 'assembled') {
      part.position.copy(original.position);
      part.quaternion.copy(original.quaternion);
      part.scale.copy(original.scale);
      this.guitarState.set('assembled');
      return { status: 'applied' };
    }
    // The guitar was authored with the soundboard as a removable mesh and braces below it.
    // Lift along its local +Y axis to expose the interior without changing any other mesh.
    part.position.copy(original.position).add(new THREE.Vector3(0, this.modelRadius * CURATED_ASSEMBLY_MANIFEST.revealOffsetFraction, 0));
    this.guitarState.set('separated');
    return { status: 'applied' };
  }

  toggleGuitarAssembly(): void {
    const state = this.guitarState() === 'assembled' ? 'separated' : 'assembled';
    this.applyAssemblyAction({ modelId: 'guitarra-acustica', partId: 'tapa-armonica', state });
  }

  async toggleHands(): Promise<void> {
    if (this.handsEnabled()) { this.stopHands('Control de manos detenido.'); return; }
    await this.startHands();
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    this.stopHands('Cámara detenida.');
    this.setLifecycle('destroyed');
    cancelAnimationFrame(this.animationFrame);
    this.resizeObserver?.disconnect();
    this.controls?.dispose();
    this.transformControls?.dispose();
    this.canvasRef()?.nativeElement.removeEventListener('click', this.canvasClickHandler);
    if (this.transformHelper) this.scene.remove(this.transformHelper);
    this.restoreAllHighlights();
    this.clearAnnotations();
    if (this.model) this.disposeObject(this.model);
    this.renderer?.dispose();
  }

  private async startHands(): Promise<void> {
    if (!navigator.mediaDevices?.getUserMedia) {
      this.handsStatus.set('La cámara requiere permiso y un contexto seguro (localhost o HTTPS).');
      return;
    }
    const requestId = ++this.handRequestId;
    this.handsEnabled.set(true);
    this.handsStatus.set('Solicitando cámara…');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
      if (this.destroyed || requestId !== this.handRequestId) { stream.getTracks().forEach((track) => track.stop()); return; }
      this.handStream = stream;
      const video = this.handVideoRef()?.nativeElement;
      if (!video) { this.stopHands('El visor no está listo para usar la cámara.'); return; }
      video.srcObject = stream;
      await video.play();
      const vision = await loadMediaPipeVision();
      if (this.destroyed || requestId !== this.handRequestId) { stream.getTracks().forEach((track) => track.stop()); return; }
      const files = await vision.FilesetResolver.forVisionTasks('https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm');
      const modelAssetPath = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task';
      try {
        this.handTask = await vision.HandLandmarker.createFromOptions(files, handLandmarkerOptions(modelAssetPath, 'GPU'));
      } catch {
        this.handTask = await vision.HandLandmarker.createFromOptions(files, handLandmarkerOptions(modelAssetPath, 'CPU'));
      }
      if (this.destroyed || requestId !== this.handRequestId) { this.handTask.close(); this.handTask = undefined; stream.getTracks().forEach((track) => track.stop()); return; }
      stream.getVideoTracks()[0]?.addEventListener('ended', () => this.stopHands('La cámara se detuvo.'), { once: true });
      this.handsStatus.set('Manos activas · puño para orbitar · separa ambas manos para acercar · índice y pinza para seleccionar.');
      this.handFrame();
    } catch (error: unknown) {
      const message = error instanceof Error && error.name === 'NotAllowedError'
        ? 'Permite el acceso a la cámara para usar gestos.'
        : 'No se pudo iniciar el seguimiento de manos. El mouse sigue disponible.';
      this.stopHands(message);
    }
  }

  private handFrame(): void {
    if (!this.handTask || !this.handStream || this.destroyed) return;
    const video = this.handVideoRef()?.nativeElement;
    if (!video) { this.stopHands('El visor no está listo para usar la cámara.'); return; }
    if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
      let frame: { readonly landmarks?: readonly (readonly HandLandmark[])[] };
      try { frame = this.handTask.detectForVideo(video, performance.now()); }
      catch { this.stopHands('Se perdió el seguimiento. El mouse sigue disponible.'); return; }
      const output = this.handTracker.update(frame.landmarks ?? [], performance.now());
      this.reticle.set(output.reticle);
      if (output.orbit) this.orbit(output.orbit.azimuthRadians, output.orbit.polarRadians);
      if (output.zoomFactor !== 1) this.zoom(output.zoomFactor);
      if (output.reticle) this.updateHoverAt(output.reticle);
      else this.setHover(undefined);
      if (output.selected && output.reticle) this.selectAt(output.reticle);
      if (output.visibleHands === 0) this.handsStatus.set('No detecto una mano. Muéstrala frente a la cámara.');
      else if (output.visibleHands > 1) this.handsStatus.set('Manos activas · puño para orbitar · separa/acerca ambas manos para zoom.');
    }
    this.handAnimationFrame = requestAnimationFrame(() => this.handFrame());
  }

  private stopHands(message: string): void {
    this.handRequestId++;
    if (this.handAnimationFrame) cancelAnimationFrame(this.handAnimationFrame);
    this.handAnimationFrame = 0;
    this.handTask?.close();
    this.handTask = undefined;
    this.handStream?.getTracks().forEach((track) => track.stop());
    this.handStream = undefined;
    const video = this.handVideoRef()?.nativeElement;
    if (video) { video.pause(); video.srcObject = null; }
    this.handTracker.reset();
    this.reticle.set(null);
    this.setHover(undefined);
    this.handsEnabled.set(false);
    this.handsStatus.set(message);
  }

  private updateHoverAt(point: { readonly x: number; readonly y: number }): void {
    this.setHover(this.raycastAt(point.x, point.y) ?? undefined);
  }

  private raycastAt(x: number, y: number): THREE.Mesh | null {
    if (!this.camera || !this.model || !Number.isFinite(x) || !Number.isFinite(y) || x < 0 || x > 1 || y < 0 || y > 1) return null;
    this.camera.updateMatrixWorld();
    this.model.updateMatrixWorld(true);
    this.raycaster.setFromCamera(new THREE.Vector2(x * 2 - 1, 1 - y * 2), this.camera);
    const hit = this.raycaster.intersectObject(this.model, true).find((intersection) =>
      (intersection.object as THREE.Mesh).isMesh && !this.isAnnotationNode(intersection.object),
    );
    if (!hit) { this.lastRayHit = null; return null; }
    const mesh = hit.object as THREE.Mesh;
    const normal = hit.face?.normal.clone() ?? new THREE.Vector3(0, 1, 0);
    normal.applyMatrix3(new THREE.Matrix3().getNormalMatrix(mesh.matrixWorld)).normalize();
    this.lastRayHit = { point: hit.point.clone(), normal };
    return mesh;
  }

  /** Finds the camera-facing surface of a semantic mesh so tutor annotations never float at its bounding-box center. */
  private surfacePointFacingCamera(mesh: THREE.Mesh): { readonly point: THREE.Vector3; readonly normal: THREE.Vector3 } | null {
    if (!this.camera) return null;
    mesh.updateWorldMatrix(true, false);
    this.camera.updateMatrixWorld();
    const bounds = new THREE.Box3().setFromObject(mesh);
    if (bounds.isEmpty()) return null;
    const center = bounds.getCenter(new THREE.Vector3());
    const rayDirection = center.sub(this.camera.position).normalize();
    if (rayDirection.lengthSq() === 0) return null;
    this.raycaster.set(this.camera.position, rayDirection);
    const hit = this.raycaster.intersectObject(mesh, false).find((intersection) => intersection.face);
    if (!hit?.face) return null;
    const normal = hit.face.normal.clone().applyMatrix3(new THREE.Matrix3().getNormalMatrix(mesh.matrixWorld)).normalize();
    return { point: hit.point.clone(), normal };
  }

  private setHover(mesh: THREE.Mesh | undefined): void {
    if (mesh === this.hoveredMesh) return;
    if (this.hoveredMesh) this.highlightMesh(this.hoveredMesh, false);
    this.hoveredMesh = mesh;
    if (mesh) this.highlightMesh(mesh, true);
  }

  private selectionFor(mesh: THREE.Mesh): CanvasSelection {
    this.getSceneSummary();
    return {
      nodePath: this.sceneNodePaths.get(mesh) ?? `/${mesh.name || 'Malla'}`,
      name: mesh.name || 'Malla sin nombre',
      kind: 'mesh',
    };
  }

  private nodePath(node: THREE.Object3D): string {
    const segments: string[] = [];
    let current: THREE.Object3D | null = node;
    while (current) {
      const index = current.parent ? current.parent.children.indexOf(current) : 0;
      segments.push(`${current.name || current.type}[${index}]`);
      current = current.parent === this.model ? null : current.parent;
    }
    return `/${segments.reverse().join('/')}`;
  }

  private sceneNodePathsTarget(path: string): THREE.Object3D | null {
    for (const [node, nodePath] of this.sceneNodePaths) if (nodePath === path) return node;
    return null;
  }

  private isAnnotationNode(node: THREE.Object3D): boolean {
    let current: THREE.Object3D | null = node;
    while (current && current !== this.model) {
      if ([...this.annotations.values()].some((annotation) => annotation === current)) return true;
      current = current.parent;
    }
    return false;
  }

  private firstMesh(node: THREE.Object3D): THREE.Mesh | null {
    let found: THREE.Mesh | null = null;
    node.traverse((child) => { if (!found && (child as THREE.Mesh).isMesh) found = child as THREE.Mesh; });
    return found;
  }

  private focusObject(object: THREE.Object3D): void {
    if (!this.camera || !this.controls) return;
    const bounds = new THREE.Box3().setFromObject(object);
    if (bounds.isEmpty()) return;
    const sphere = bounds.getBoundingSphere(new THREE.Sphere());
    const direction = this.camera.position.clone().sub(this.controls.target);
    const radius = Math.max(sphere.radius, this.modelRadius * 0.0001);
    const distance = radius / Math.sin(THREE.MathUtils.degToRad(this.camera.fov / 2)) * 1.55;
    const normalizedDirection = direction.lengthSq() > 0 ? direction.normalize() : new THREE.Vector3(0, 0, 1);
    const toTarget = sphere.center.clone();
    const toPosition = sphere.center.clone().add(normalizedDirection.multiplyScalar(distance));
    this.setCameraScale(radius, distance);
    this.cameraTransition = {
      startedAt: performance.now(),
      durationMs: 900,
      fromPosition: this.camera.position.clone(),
      toPosition,
      fromTarget: this.controls.target.clone(),
      toTarget,
    };
  }

  private addAnchoredAnnotation(mesh: THREE.Mesh, worldPoint: THREE.Vector3, label: string): void {
    mesh.updateWorldMatrix(true, false);
    const localPoint = mesh.worldToLocal(worldPoint.clone());
    const group = new THREE.Group();
    const meshBounds = new THREE.Box3().setFromObject(mesh);
    const meshRadius = Math.max(meshBounds.getBoundingSphere(new THREE.Sphere()).radius, this.modelRadius * 0.025);
    const cameraRight = new THREE.Vector3(1, 0, 0).applyQuaternion(this.camera?.quaternion ?? new THREE.Quaternion());
    const cameraUp = new THREE.Vector3(0, 1, 0).applyQuaternion(this.camera?.quaternion ?? new THREE.Quaternion());
    const worldOffset = cameraRight.multiplyScalar(meshRadius * 0.36).add(cameraUp.multiplyScalar(meshRadius * 0.24));
    const localOffset = worldOffset.applyMatrix3(new THREE.Matrix3().setFromMatrix4(mesh.matrixWorld).invert());
    const arrowLength = Math.max(localOffset.length(), meshRadius * 0.12);
    const arrowStart = localPoint.clone().add(localOffset);
    const pin = new THREE.Mesh(
      new THREE.SphereGeometry(meshRadius * 0.025, 12, 8),
      new THREE.MeshBasicMaterial({ color: 0xe76f00, depthTest: false }),
    );
    pin.position.copy(localPoint);
    pin.renderOrder = 1001;
    group.add(pin);
    // Place the label beside the marked surface; the arrowhead terminates exactly at the tutor's target.
    const arrow = new THREE.ArrowHelper(localPoint.clone().sub(arrowStart).normalize(), arrowStart, arrowLength, 0xe76f00, arrowLength * 0.25, arrowLength * 0.16);
    (arrow.line.material as THREE.LineBasicMaterial).depthTest = false;
    (arrow.cone.material as THREE.MeshBasicMaterial).depthTest = false;
    arrow.line.renderOrder = 1001;
    arrow.cone.renderOrder = 1001;
    group.add(arrow);
    const compactLabel = label.length > 30 ? `${label.slice(0, 27).trimEnd()}…` : label;
    const sprite = this.createLabel(compactLabel);
    sprite.position.copy(arrowStart).add(localOffset.clone().normalize().multiplyScalar(meshRadius * 0.12));
    sprite.scale.set(meshRadius * 0.3, meshRadius * 0.075, 1);
    sprite.renderOrder = 1002;
    group.add(sprite);
    mesh.add(group);
    const id = `locator-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    this.annotations.set(id, group);
  }

  private initialize(): void {
    if (this.destroyed) return;
    const canvas = this.canvasRef()?.nativeElement;
    if (!canvas) {
      this.loading.set(false);
      this.error.set('No se pudo encontrar la superficie del visor 3D.');
      this.setLifecycle('failed');
      return;
    }
    try {
      this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      this.renderer.setClearColor(0xffffff);
      this.scene.background = new THREE.Color(0xffffff);
      this.camera = new THREE.PerspectiveCamera(42, 1, 0.01, 1000);
      this.camera.position.set(0, 0.6, 3.3);
      this.scene.add(new THREE.HemisphereLight(0xffffff, 0x8794a5, 2.1));
      const keyLight = new THREE.DirectionalLight(0xffffff, 2.4);
      keyLight.position.set(4, 6, 5);
      this.scene.add(keyLight);
      this.controls = new OrbitControls(this.camera, canvas);
      this.controls.enableDamping = true;
      this.controls.dampingFactor = 0.08;
      this.controls.minDistance = 0.1;
      this.controls.maxDistance = 50;
      this.transformControls = new TransformControls(this.camera, canvas);
      this.transformControls.setMode('translate');
      this.transformControls.size = 0.85;
      this.transformHelper = this.transformControls.getHelper();
      this.scene.add(this.transformHelper);
      this.transformControls.addEventListener('dragging-changed', (event) => {
        this.transformInteraction = Boolean(event.value);
        if (this.controls) this.controls.enabled = !this.transformInteraction;
        if (!this.transformInteraction) this.ignoreClickUntil = performance.now() + 220;
      });
      canvas.addEventListener('click', this.canvasClickHandler);
      this.observeSize();
      this.renderLoop();
      void this.loadModel(this.src());
    } catch {
      this.loading.set(false);
      this.error.set('No se pudo iniciar el visor 3D en este navegador.');
      this.setLifecycle('failed');
    }
  }

  private async loadModel(url: string): Promise<void> {
    try {
      const gltf = await this.loader.loadAsync(url);
      if (this.destroyed) {
        this.disposeObject(gltf.scene);
        return;
      }
      this.model = gltf.scene;
      this.scene.add(gltf.scene);
      this.fitCamera(gltf.scene);
      this.loading.set(false);
      this.setLifecycle('ready');
    } catch {
      if (this.destroyed) return;
      this.loading.set(false);
      this.error.set('No se pudo abrir este GLB. Verifica que el archivo sea válido e inténtalo de nuevo.');
      this.setLifecycle('failed');
    }
  }

  private fitCamera(object: THREE.Object3D): void {
    if (!this.camera || !this.controls) return;
    const bounds = new THREE.Box3().setFromObject(object);
    const sphere = bounds.getBoundingSphere(new THREE.Sphere());
    this.modelRadius = Math.max(sphere.radius, 0.0001);
    this.fitSphere(sphere, this.modelRadius, new THREE.Vector3(0.08, 0.2, 1));
  }

  private fitSphere(sphere: THREE.Sphere, radius: number, direction: THREE.Vector3): void {
    if (!this.camera || !this.controls) return;
    const safeRadius = Math.max(radius, 0.0001);
    const distance = safeRadius / Math.sin(THREE.MathUtils.degToRad(this.camera.fov / 2)) * 1.15;
    this.controls.target.copy(sphere.center);
    this.camera.position.copy(sphere.center).add(direction.clone().normalize().multiplyScalar(distance));
    this.setCameraScale(safeRadius, distance);
    this.controls.update();
  }

  private setCameraScale(radius: number, distance: number): void {
    if (!this.camera || !this.controls) return;
    const scale = cameraScaleForRadius(radius);
    this.controls.minDistance = scale.minDistance;
    this.controls.maxDistance = scale.maxDistance;
    this.camera.near = scale.nearPlane;
    this.camera.far = Math.max(scale.farPlane, distance + Math.abs(radius) * 10);
    this.camera.updateProjectionMatrix();
  }

  private zoom(factor: number): CanvasCommandResult {
    if (!this.camera || !this.controls) return this.notReadyResult();
    this.cameraTransition = null;
    const offset = this.camera.position.clone().sub(this.controls.target);
    const distance = THREE.MathUtils.clamp(
      offset.length() / factor,
      this.controls.minDistance,
      this.controls.maxDistance,
    );
    if (offset.lengthSq() === 0) offset.set(0, 0, 1);
    this.camera.position.copy(this.controls.target).add(offset.normalize().multiplyScalar(distance));
    this.controls.update();
    return { status: 'applied' };
  }

  private orbit(azimuthRadians: number, polarRadians: number): CanvasCommandResult {
    if (!this.camera || !this.controls) return this.notReadyResult();
    this.cameraTransition = null;
    const offset = this.camera.position.clone().sub(this.controls.target);
    const spherical = new THREE.Spherical().setFromVector3(offset);
    spherical.theta -= azimuthRadians;
    spherical.phi = THREE.MathUtils.clamp(spherical.phi + polarRadians, 0.0001, Math.PI - 0.0001);
    this.camera.position.copy(this.controls.target).add(new THREE.Vector3().setFromSpherical(spherical));
    this.camera.lookAt(this.controls.target);
    this.controls.update();
    return { status: 'applied' };
  }

  private setPreset(preset: 'front' | 'back' | 'left' | 'right' | 'top'): CanvasCommandResult {
    if (!this.camera || !this.controls) return this.notReadyResult();
    const directions: Record<typeof preset, THREE.Vector3> = {
      front: new THREE.Vector3(0, 0.08, 1),
      back: new THREE.Vector3(0, 0.08, -1),
      left: new THREE.Vector3(-1, 0.08, 0),
      right: new THREE.Vector3(1, 0.08, 0),
      top: new THREE.Vector3(0, 1, 0.0001),
    };
    this.camera.up.copy(preset === 'top' ? new THREE.Vector3(0, 0, -1) : new THREE.Vector3(0, 1, 0));
    const center = this.controls.target.clone();
    const distance = this.modelRadius / Math.sin(THREE.MathUtils.degToRad(this.camera.fov / 2)) * 1.15;
    this.camera.position.copy(center).add(directions[preset].normalize().multiplyScalar(distance));
    this.camera.lookAt(center);
    this.setCameraScale(this.modelRadius, distance);
    this.controls.update();
    return { status: 'applied' };
  }

  private focus(target: Extract<CanvasCommand, { type: 'camera.focus' }>['target']): CanvasCommandResult {
    if (!this.model) return this.notReadyResult();
    if (target.kind === 'model') {
      this.fitCamera(this.model);
      return { status: 'applied' };
    }
    const matches: THREE.Object3D[] = [];
    this.model.traverse((node) => {
      if (node.name === target.nodeName) matches.push(node);
    });
    if (matches.length !== 1) {
      return {
        status: 'unsupported-target',
        target: target.nodeName,
        reason: matches.length === 0 ? 'No existe una pieza con ese nombre.' : 'El nombre identifica varias piezas.',
      };
    }
    const bounds = new THREE.Box3().setFromObject(matches[0]);
    if (bounds.isEmpty()) {
      return { status: 'unsupported-target', target: target.nodeName, reason: 'La pieza no tiene volumen visible.' };
    }
    const sphere = bounds.getBoundingSphere(new THREE.Sphere());
    const currentDirection = this.camera && this.controls
      ? this.camera.position.clone().sub(this.controls.target)
      : new THREE.Vector3(0.08, 0.2, 1);
    const radius = Math.max(sphere.radius, this.modelRadius * 0.0001);
    this.fitSphere(sphere, radius, currentDirection);
    return { status: 'applied' };
  }

  private setHighlight(nodeName: string, active: boolean): CanvasCommandResult {
    if (!this.model) return { status: 'not-ready', state: 'loading' };
    const matches: THREE.Mesh[] = [];
    this.model.traverse((node) => {
      const mesh = node as THREE.Mesh;
      if (mesh.isMesh && mesh.name === nodeName) matches.push(mesh);
    });
    if (matches.length !== 1) {
      return {
        status: 'unsupported-target',
        target: nodeName,
        reason: matches.length === 0 ? 'No existe una malla con ese nombre.' : 'El nombre identifica varias mallas.',
      };
    }
    const mesh = matches[0];
    this.highlightMesh(mesh, active);
    return { status: 'applied' };
  }

  private highlightMesh(mesh: THREE.Mesh, active: boolean): void {
    if (!active) { this.restoreHighlight(mesh); return; }
    if (this.highlighted.has(mesh)) return;
    const original = mesh.material;
    const replacements = (Array.isArray(original) ? original : [original]).map((material) => {
      const clone = material.clone();
      const tintable = clone as THREE.Material & { color?: THREE.Color; emissive?: THREE.Color; emissiveIntensity?: number };
      if (tintable.emissive) {
        tintable.emissive.set(0xffb300);
        if (typeof tintable.emissiveIntensity === 'number') tintable.emissiveIntensity = Math.max(tintable.emissiveIntensity, 0.7);
      } else if (tintable.color) {
        tintable.color.lerp(new THREE.Color(0xffc107), 0.55);
      }
      return clone;
    });
    const replacement = Array.isArray(original) ? replacements : replacements[0];
    mesh.material = replacement;
    this.highlighted.set(mesh, { original, replacement });
  }

  private restoreHighlight(mesh: THREE.Mesh): void {
    const highlight = this.highlighted.get(mesh);
    if (!highlight) return;
    mesh.material = highlight.original;
    (Array.isArray(highlight.replacement) ? highlight.replacement : [highlight.replacement])
      .forEach((material) => material.dispose());
    this.highlighted.delete(mesh);
  }

  private restoreAllHighlights(): void {
    for (const mesh of this.highlighted.keys()) this.restoreHighlight(mesh);
  }

  private createLabel(label: string): THREE.Sprite {
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    if (!context) throw new Error('No se pudo crear la etiqueta del canvas.');
    const fontSize = 34;
    context.font = `600 ${fontSize}px sans-serif`;
    const width = Math.ceil(context.measureText(label).width + 48);
    canvas.width = Math.max(width, 120);
    canvas.height = 72;
    context.font = `600 ${fontSize}px sans-serif`;
    context.fillStyle = '#fffdf7';
    context.strokeStyle = '#e76f00';
    context.lineWidth = 5;
    context.beginPath();
    context.roundRect(3, 3, canvas.width - 6, canvas.height - 6, 20);
    context.fill();
    context.stroke();
    context.fillStyle = '#27313f';
    context.textBaseline = 'middle';
    context.fillText(label, 24, canvas.height / 2, canvas.width - 48);
    const texture = new THREE.CanvasTexture(canvas);
    const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false });
    return new THREE.Sprite(material);
  }

  private clearAnnotations(id?: string): CanvasCommandResult {
    if (id) {
      const annotation = this.annotations.get(id);
      if (!annotation) return { status: 'unsupported-target', target: id, reason: 'No existe esa anotación.' };
      annotation.parent?.remove(annotation);
      this.disposeObject(annotation);
      this.annotations.delete(id);
      return { status: 'applied' };
    }
    for (const annotation of this.annotations.values()) {
      annotation.parent?.remove(annotation);
      this.disposeObject(annotation);
    }
    this.annotations.clear();
    return { status: 'applied' };
  }

  private setLifecycle(state: CanvasLifecycleState): void {
    this.lifecycle = state;
    if (state !== 'loading' && !this.settledReadiness) {
      this.settledReadiness = true;
      this.resolveReadiness(state);
    }
  }

  private notReadyResult(): CanvasCommandResult {
    const state = this.lifecycle;
    return { status: 'not-ready', state: state === 'ready' ? 'loading' : state };
  }

  private observeSize(): void {
    const canvas = this.canvasRef()?.nativeElement;
    if (!canvas) return;
    const resize = () => {
      if (!this.renderer || !this.camera) return;
      const bounds = canvas.getBoundingClientRect();
      if (!bounds.width || !bounds.height) return;
      this.renderer.setSize(bounds.width, bounds.height, false);
      this.camera.aspect = bounds.width / bounds.height;
      this.camera.updateProjectionMatrix();
    };
    this.resizeObserver = new ResizeObserver(resize);
    this.resizeObserver.observe(canvas.parentElement ?? canvas);
    resize();
  }

  private renderLoop(): void {
    if (this.destroyed) return;
    this.animationFrame = requestAnimationFrame(() => this.renderLoop());
    this.updateCameraTransition();
    this.controls?.update();
    if (this.renderer && this.camera) this.renderer.render(this.scene, this.camera);
  }

  private updateCameraTransition(): void {
    const transition = this.cameraTransition;
    if (!transition || !this.camera || !this.controls) return;
    const rawProgress = THREE.MathUtils.clamp((performance.now() - transition.startedAt) / transition.durationMs, 0, 1);
    const easedProgress = rawProgress * rawProgress * (3 - 2 * rawProgress);
    this.camera.position.lerpVectors(transition.fromPosition, transition.toPosition, easedProgress);
    this.controls.target.lerpVectors(transition.fromTarget, transition.toTarget, easedProgress);
    this.camera.lookAt(this.controls.target);
    if (rawProgress >= 1) this.cameraTransition = null;
  }

  private disposeObject(object: THREE.Object3D): void {
    const geometries = new Set<THREE.BufferGeometry>();
    const materials = new Set<THREE.Material>();
    const textures = new Set<THREE.Texture>();
    object.traverse((child) => {
      const drawable = child as THREE.Mesh | THREE.Line | THREE.LineSegments;
      if ('geometry' in drawable && drawable.geometry) geometries.add(drawable.geometry as THREE.BufferGeometry);
      if (!('material' in drawable) || !drawable.material) return;
      const meshMaterials = Array.isArray(drawable.material) ? drawable.material : [drawable.material];
      for (const material of meshMaterials as THREE.Material[]) {
        materials.add(material);
        for (const value of Object.values(material)) {
          if (value instanceof THREE.Texture) textures.add(value);
        }
      }
    });
    geometries.forEach((geometry) => geometry.dispose());
    materials.forEach((material) => material.dispose());
    textures.forEach((texture) => texture.dispose());
  }
}

const MEDIAPIPE_VISION_URL = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/vision_bundle.mjs';

async function loadMediaPipeVision(): Promise<MediaPipeVisionModule> {
  // Downloaded only after the student presses “Manos”; no camera/model code loads at startup.
  const moduleUrl: string = MEDIAPIPE_VISION_URL;
  return await import(/* @vite-ignore */ moduleUrl) as MediaPipeVisionModule;
}

function handLandmarkerOptions(modelAssetPath: string, delegate: 'GPU' | 'CPU'): Record<string, unknown> {
  return {
    baseOptions: { modelAssetPath, delegate },
    runningMode: 'VIDEO',
    numHands: 2,
    minHandDetectionConfidence: 0.55,
    minHandPresenceConfidence: 0.55,
    minTrackingConfidence: 0.55,
  };
}
