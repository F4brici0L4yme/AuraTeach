import { HttpErrorResponse } from '@angular/common/http';
import { Component, HostListener, OnDestroy, inject, signal, viewChild } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { MatButton } from '@angular/material/button';
import { ModelCatalogApi, CatalogModel } from '../model-catalog/model-catalog-api';
import { LocalModelLaunch } from '../model-catalog/local-model-launch';
import { GlbViewport } from './glb-viewport';
import { TutorPanel } from '../tutoring/tutor-panel';
import { StudentActivityApi } from '../analytics/student-activity-api';
import type { CanvasAssemblyAction, CanvasLocator } from './canvas-scene';

@Component({
  selector: 'app-exploration-page',
  imports: [GlbViewport, MatButton, TutorPanel],
  template: `
    <main class="exploration-page">
      <h1 class="visually-hidden">Exploración 3D: {{ title() }}</h1>
      @if (topic()) { <p class="visually-hidden">Tema: {{ topic() }}</p> }
      @if (loading()) {
        <div class="page-message" role="status" aria-live="polite">Preparando el modelo…</div>
      } @else if (error()) {
        <div class="page-message error" role="alert">
          <p>{{ error() }}</p>
          <button mat-button type="button" (click)="back()">Volver a la biblioteca</button>
        </div>
      } @else if (assetUrl()) {
        <app-glb-viewport #viewer [src]="assetUrl()!" [modelId]="modelId()"
          (selectionChanged)="selectedNodePath.set($event?.nodePath ?? null)" />
        <app-tutor-panel
          [modelId]="modelId()"
          [topic]="topic()"
          [selectedNodePath]="selectedNodePath()"
          [sceneNodes]="tutorSceneNodes()"
          [sceneParts]="tutorSceneParts()"
          [screenshot]="captureFrame"
          (locator)="applyTutorLocator($event)"
          (sceneAction)="applyTutorSceneAction($event)"
        />
        @if (canvasNotice()) { <div class="canvas-notice" role="status">{{ canvasNotice() }}</div> }
      }
    </main>
  `,
  styles: `
    :host { display: block; position: fixed; inset: 0; z-index: 1; width: 100%; height: 100vh; height: 100dvh; overflow: hidden; color: #172033; background: #fff; }
    .exploration-page { position: relative; width: 100%; height: 100%; overflow: hidden; background: #fff; }
    app-glb-viewport { position: absolute; inset: 0; display: block; width: 100%; height: 100%; }
    .visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
    .page-message { position: absolute; inset: 0; z-index: 1; display: grid; place-content: center; justify-items: center; gap: 12px; padding: 24px; color: #526078; text-align: center; background: #fff; }
    .page-message p { max-width: 36rem; margin: 0; }
    .error { color: #9b1c1c; }
    .canvas-notice { position:absolute; top:18px; left:50%; z-index:5; transform:translateX(-50%); max-width:min(90vw,620px); padding:10px 16px; border:1px solid #ead4a9; border-radius:12px; color:#6d4b16; background:#fff8e8; box-shadow:0 3px 14px #17203318; font-size:13px; text-align:center; }
  `,
})
export class ExplorationPage implements OnDestroy {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(ModelCatalogApi);
  private readonly localLaunch = inject(LocalModelLaunch);
  private readonly activityApi = inject(StudentActivityApi);
  private readonly viewport = viewChild(GlbViewport);
  private localUrl: string | null = null;

  protected readonly title = signal('Modelo 3D');
  protected readonly topic = signal('');
  protected readonly modelId = signal('');
  protected readonly assetUrl = signal<string | null>(null);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly canvasNotice = signal('');
  protected readonly selectedNodePath = signal<string | null>(null);

  protected readonly captureFrame = (): string | null => this.viewport()?.captureSceneFrame() ?? null;

  constructor() {
    const modelId = this.route.snapshot.paramMap.get('modelId');
    if (modelId === 'local') {
      const file = this.localLaunch.take();
      if (!file) {
        this.loading.set(false);
        this.error.set('El modelo local ya no está disponible. Vuelve a seleccionarlo desde la biblioteca.');
        return;
      }
      this.localUrl = URL.createObjectURL(file);
      this.modelId.set('local');
      this.title.set(file.name);
      this.topic.set('Modelo local · este archivo no se sube ni se guarda.');
      this.assetUrl.set(this.localUrl);
      this.loading.set(false);
      return;
    }

    if (!modelId) {
      this.loading.set(false);
      this.error.set('No se indicó un modelo.');
      return;
    }

    this.api.get(modelId).subscribe({
      next: (model: CatalogModel) => {
        this.modelId.set(model.id);
        this.title.set(model.title);
        this.topic.set(model.topic);
        this.assetUrl.set(model.assetUrl);
        this.loading.set(false);
        this.activityApi.recordModelVisit(model.id).subscribe({ error: () => undefined });
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(error instanceof HttpErrorResponse && error.status === 404
          ? 'Este modelo ya no está en la biblioteca.'
          : 'No pudimos abrir el modelo. Comprueba tu conexión e inténtalo de nuevo.');
      },
    });
  }

  ngOnDestroy(): void {
    if (this.localUrl) URL.revokeObjectURL(this.localUrl);
  }

  @HostListener('window:keydown', ['$event'])
  protected onWindowKeydown(event: KeyboardEvent): void {
    if (event.key !== 'Escape' || event.defaultPrevented) return;
    event.preventDefault();
    this.back();
  }

  protected back(): void {
    void this.router.navigateByUrl('/alumno');
  }

  protected tutorSceneNodes() {
    return (this.viewport()?.getSceneSummary().nodes ?? []).slice(0, 120).map((node) => ({
      nodePath: node.nodePath,
      name: node.name,
      type: node.kind === 'mesh' ? 'mesh' as const : 'group' as const,
    }));
  }

  protected tutorSceneParts() {
    return this.modelId() === 'guitarra-acustica'
      ? [{ partId: 'tapa-armonica', label: 'Tapa armónica desmontable' }]
      : [];
  }

  protected applyTutorLocator(locator: NonNullable<import('../tutoring/tutor-api').TutorAnswer['locator']>): void {
    const canvas = this.viewport();
    if (!canvas || locator.kind === 'none') return;
    const normalized: CanvasLocator = locator.kind === 'semantic-node'
      ? { kind: 'semantic-node', nodePath: locator.nodePath }
      : { kind: 'image-point', viewId: locator.viewId, uv: locator.uv };
    const result = canvas.applyLocator(normalized, locator.label);
    this.canvasNotice.set(result.status === 'applied' ? '' : 'No pude ubicar esa parte con seguridad en el modelo actual. Rótalo o señala la zona y vuelve a preguntar.');
  }

  protected applyTutorSceneAction(action: NonNullable<import('../tutoring/tutor-api').TutorAnswer['sceneAction']>): void {
    const canvas = this.viewport();
    if (!canvas || action.kind === 'none') return;
    const request: CanvasAssemblyAction = {
      modelId: this.modelId(),
      partId: action.kind === 'assemble' ? 'tapa-armonica' : action.partId,
      state: action.kind === 'assemble' ? 'assembled' : 'separated',
    };
    const result = canvas.applyAssemblyAction(request);
    this.canvasNotice.set(result.status === 'applied' ? '' : 'Esa acción no está disponible para las piezas verificadas de este modelo.');
  }
}
