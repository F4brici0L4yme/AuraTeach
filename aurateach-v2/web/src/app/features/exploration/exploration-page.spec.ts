import { provideRouter, Router } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { Component, input, output } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { NEVER, of, throwError } from 'rxjs';
import { ExplorationPage } from './exploration-page';
import { ModelCatalogApi } from '../model-catalog/model-catalog-api';
import { LocalModelLaunch } from '../model-catalog/local-model-launch';
import { GlbViewport } from './glb-viewport';
import { API_BASE_URL } from '../../core/api/api-base-url';
import { StudentActivityApi } from '../analytics/student-activity-api';

@Component({ template: '<p>Catálogo de modelos</p>' })
class CatalogStub {}

@Component({ selector: 'app-glb-viewport', template: '<div data-testid="viewer-stub">Visor 3D</div>' })
class GlbViewportStub {
  readonly src = input.required<string>();
  readonly modelId = input<string | null>(null);
  readonly selectionChanged = output<{ nodePath: string } | null>();
}

const model = {
  id: 'model-1',
  title: 'Modelo de prueba',
  topic: 'Ciencias',
  source: 'Escuela',
  license: 'CC BY 4.0',
  thumbnailUrl: '/model.png',
  assetUrl: '/model.glb',
  visitCount: 0,
};

describe('student model exploration page', () => {
  let harness: RouterTestingHarness;
  let getModel: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    getModel = vi.fn().mockReturnValue(of(model));
    TestBed.configureTestingModule({
      imports: [CatalogStub],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '' },
        { provide: StudentActivityApi, useValue: { recordModelVisit: () => of(undefined) } },
        provideRouter([
          { path: 'alumno', component: CatalogStub },
          { path: 'alumno/exploracion/:modelId', component: ExplorationPage },
        ]),
        { provide: ModelCatalogApi, useValue: { get: getModel } },
        { provide: LocalModelLaunch, useValue: { take: () => null } },
      ],
    });
    TestBed.overrideComponent(ExplorationPage, {
      remove: { imports: [GlbViewport] },
      add: { imports: [GlbViewportStub] },
    });
    harness = await RouterTestingHarness.create();
  });

  it('returns to the student catalog when Escape is pressed', async () => {
    await harness.navigateByUrl('/alumno/exploracion/model-1', ExplorationPage);

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    await harness.fixture.whenStable();

    expect(TestBed.inject(Router).url).toBe('/alumno');
    expect(harness.routeNativeElement?.textContent).toContain('Catálogo de modelos');
  });

  it('does not leave the canvas for unrelated keys and removes the Escape listener after navigation', async () => {
    await harness.navigateByUrl('/alumno/exploracion/model-1', ExplorationPage);

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    await harness.fixture.whenStable();
    expect(TestBed.inject(Router).url).toBe('/alumno/exploracion/model-1');

    await harness.navigateByUrl('/alumno', CatalogStub);
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    await harness.fixture.whenStable();
    expect(TestBed.inject(Router).url).toBe('/alumno');
  });

  it('keeps accessible loading and error states with a catalog return action', async () => {
    getModel.mockReturnValueOnce(NEVER);
    await harness.navigateByUrl('/alumno/exploracion/model-1', ExplorationPage);
    expect((harness.routeNativeElement as HTMLElement).querySelector('[role="status"]')?.textContent)
      .toContain('Preparando el modelo');

    await harness.navigateByUrl('/alumno', CatalogStub);
    // Change the provider for a subsequent route activation to simulate an unavailable model.
    getModel.mockReturnValueOnce(throwError(() => new Error('not found')));
    await harness.navigateByUrl('/alumno/exploracion/model-3', ExplorationPage);
    await harness.fixture.whenStable();
    const page = harness.routeNativeElement as HTMLElement;
    expect(page.querySelector('[role="alert"]')?.textContent).toContain('No pudimos abrir el modelo');
    page.querySelector<HTMLButtonElement>('button')?.click();
    await harness.fixture.whenStable();
    expect(TestBed.inject(Router).url).toBe('/alumno');
  });
});
