import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { MatButton } from '@angular/material/button';
import { MatCard, MatCardContent } from '@angular/material/card';
import { MatFormField, MatLabel } from '@angular/material/form-field';
import { MatIcon } from '@angular/material/icon';
import { MatInput } from '@angular/material/input';
import { MatProgressSpinner } from '@angular/material/progress-spinner';
import { DemoProfileSession } from '../identity/demo-profile-session';
import { CatalogModel, ModelCatalogApi } from './model-catalog-api';
import { LocalModelLaunch } from './local-model-launch';

@Component({
  selector: 'app-model-catalog-page',
  imports: [MatButton, MatCard, MatCardContent, MatFormField, MatIcon, MatInput, MatLabel, MatProgressSpinner],
  template: `
    <main class="catalog-page">
      <header class="catalog-header">
        <div>
          <p class="eyebrow">AuraTeach · Exploración</p>
          <h1>Biblioteca de modelos</h1>
          <p>Elige un modelo de la escuela o explora uno que tengas en tu dispositivo.</p>
        </div>
        <div class="header-actions">
          <span>{{ profileName() }}</span>
          <button mat-button type="button" (click)="leave()">Salir</button>
        </div>
      </header>

      <section class="catalog-tools" aria-label="Buscar modelos">
        <mat-form-field appearance="outline" class="search-field">
          <mat-label>Buscar por nombre o tema</mat-label>
          <mat-icon matPrefix aria-hidden="true">search</mat-icon>
          <input matInput [value]="search()" (input)="onSearch($event)" />
        </mat-form-field>
        <span class="catalog-count">{{ total() }} modelos</span>
      </section>

      @if (loading()) {
        <div class="catalog-status" role="status"><mat-spinner diameter="36" />Cargando biblioteca…</div>
      } @else if (error()) {
        <div class="catalog-status error-state" role="alert">
          <p>{{ error() }}</p>
          <button mat-button type="button" (click)="loadPage()">Reintentar</button>
        </div>
      } @else {
        <section class="model-grid" aria-label="Modelos disponibles">
          @if (page() === 1) {
            <button class="upload-card" type="button" data-testid="upload-model" (click)="filePicker.click()">
              <span class="upload-icon"><mat-icon aria-hidden="true">add</mat-icon></span>
              <strong>Usar mi modelo</strong>
              <span>Selecciona un archivo GLB</span>
            </button>
          }
          @for (model of models(); track model.id) {
            <button class="model-card-button" type="button" [attr.data-testid]="'model-' + model.id" (click)="openModel(model)">
              <mat-card class="model-card">
                <div class="preview-wrap">
                  <img [src]="model.thumbnailUrl" [alt]="'Vista previa de ' + model.title" loading="lazy" />
                </div>
                <mat-card-content>
                  <strong>{{ model.title }}</strong>
                  <span>{{ model.topic }}</span>
                  <small><mat-icon aria-hidden="true">visibility</mat-icon> {{ model.visitCount }} exploraciones</small>
                </mat-card-content>
              </mat-card>
            </button>
          }
          @if (models().length === 0) {
            <p class="empty-state">No encontramos modelos con esa búsqueda.</p>
          }
        </section>

        @if (pageCount() > 1) {
          <nav class="pagination" aria-label="Paginación de modelos">
            <button mat-button type="button" [disabled]="page() === 1" (click)="goToPage(page() - 1)">Anterior</button>
            <span>Página {{ page() }} de {{ pageCount() }}</span>
            <button mat-button type="button" [disabled]="page() === pageCount()" (click)="goToPage(page() + 1)">Siguiente</button>
          </nav>
        }
      }

      <input #filePicker class="visually-hidden" type="file" accept=".glb,model/gltf-binary" data-testid="local-model-picker" (change)="selectLocalModel($event)" />
    </main>
  `,
  styles: `
    :host { display: block; min-height: 100vh; color: #172033; background: #fff; }
    .catalog-page { max-width: 1440px; margin: 0 auto; padding: 28px clamp(18px, 4vw, 56px) 36px; }
    .catalog-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; }
    h1 { margin: 4px 0 8px; font-size: clamp(28px, 3vw, 40px); }
    .catalog-header p { color: #667085; margin: 0; }
    .eyebrow { text-transform: uppercase; letter-spacing: .12em; font-size: 12px; font-weight: 700; }
    .header-actions { display: flex; align-items: center; gap: 12px; }
    .catalog-tools { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin: 28px 0 20px; }
    .search-field { width: min(520px, 100%); }
    .catalog-count { color: #667085; }
    .model-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; min-height: 420px; }
    .model-card-button, .upload-card { appearance: none; border: 0; padding: 0; text-align: left; cursor: pointer; font: inherit; color: inherit; background: transparent; min-width: 0; }
    .model-card { height: 100%; overflow: hidden; background: #fff; border: 1px solid #e5e9f1; box-shadow: 0 3px 14px #1720330a; transition: transform 160ms ease, box-shadow 160ms ease; }
    .model-card-button:hover .model-card, .model-card-button:focus-visible .model-card { transform: translateY(-3px); box-shadow: 0 8px 24px #17203320; }
    .preview-wrap { height: clamp(150px, 19vw, 250px); background: #fff; display: grid; place-items: center; }
    .preview-wrap img { width: 100%; height: 100%; object-fit: contain; }
    mat-card-content { display: grid; gap: 6px; padding: 16px !important; }
    mat-card-content > span, mat-card-content small { color: #667085; }
    mat-card-content small { display: flex; align-items: center; gap: 5px; }
    mat-card-content small mat-icon { width: 17px; height: 17px; font-size: 17px; }
    .upload-card { border: 2px dashed #aab6cd; border-radius: 14px; background: white; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; min-height: 245px; text-align: center; color: #475467; }
    .upload-card:hover, .upload-card:focus-visible { border-color: #475569; background: #fafafa; }
    .upload-icon { display: grid; place-items: center; width: 54px; height: 54px; border-radius: 50%; color: white; background: #26334a; }
    .upload-icon mat-icon { width: 30px; height: 30px; font-size: 30px; }
    .pagination { display: flex; justify-content: center; align-items: center; gap: 18px; margin: 24px 0; }
    .catalog-status { display: flex; align-items: center; justify-content: center; gap: 12px; min-height: 300px; color: #667085; }
    .error-state { flex-direction: column; color: #9b1c1c; }
    .empty-state { grid-column: 1 / -1; text-align: center; padding: 50px; color: #667085; }
    .visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
    @media (max-width: 760px) { .model-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .catalog-header { flex-direction: column; } .preview-wrap { height: 180px; } }
    @media (max-width: 480px) { .model-grid { grid-template-columns: 1fr; } .catalog-tools { align-items: flex-start; flex-direction: column; } }
  `,
})
export class ModelCatalogPage {
  private readonly api = inject(ModelCatalogApi);
  private readonly router = inject(Router);
  private readonly session = inject(DemoProfileSession);
  private readonly localLaunch = inject(LocalModelLaunch);

  protected readonly models = signal<CatalogModel[]>([]);
  protected readonly page = signal(1);
  protected readonly search = signal('');
  protected readonly total = signal(0);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly pageCount = computed(() => Math.max(1, Math.ceil(Math.max(0, this.total() - 8) / 9) + 1));
  protected readonly profileName = () => this.session.current()?.displayName ?? 'Alumno';
  private requestSequence = 0;

  constructor() {
    this.loadPage();
  }

  protected onSearch(event: Event): void {
    this.search.set((event.target as HTMLInputElement).value.trim());
    this.page.set(1);
    this.loadPage();
  }

  protected goToPage(page: number): void {
    if (page < 1 || page > this.pageCount()) return;
    this.page.set(page);
    this.loadPage();
  }

  protected loadPage(): void {
    const requestSequence = ++this.requestSequence;
    this.loading.set(true);
    this.error.set(null);
    const offset = this.page() === 1 ? 0 : 8 + (this.page() - 2) * 9;
    const limit = this.page() === 1 ? 8 : 9;
    this.api.list({ offset, limit, search: this.search() || undefined }).subscribe({
      next: (response) => {
        if (requestSequence !== this.requestSequence) return;
        this.models.set(response.items);
        this.total.set(response.total);
        this.loading.set(false);
      },
      error: (error: unknown) => {
        if (requestSequence !== this.requestSequence) return;
        this.models.set([]);
        this.total.set(0);
        this.error.set(error instanceof HttpErrorResponse && error.status === 0
          ? 'No pudimos conectar con el catálogo. Comprueba que el servidor esté encendido.'
          : 'No pudimos cargar los modelos. Inténtalo de nuevo.');
        this.loading.set(false);
      },
    });
  }

  protected openModel(model: CatalogModel): void {
    void this.router.navigate(['/alumno/exploracion', model.id]);
  }

  protected selectLocalModel(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.glb')) {
      this.error.set('Selecciona un archivo .glb para continuar.');
      input.value = '';
      return;
    }
    this.localLaunch.begin(file);
    input.value = '';
    void this.router.navigate(['/alumno/exploracion', 'local']);
  }

  protected leave(): void {
    this.session.leave();
    void this.router.navigateByUrl('/');
  }
}
