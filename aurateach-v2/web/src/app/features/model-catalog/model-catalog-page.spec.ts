import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { API_BASE_URL } from '../../core/api/api-base-url';
import { routes } from '../../app.routes';
import { DemoProfileSession } from '../identity/demo-profile-session';
import { CatalogModel, ModelCatalogResponse } from './model-catalog-api';
import { LocalModelLaunch } from './local-model-launch';
import { GlbViewport } from '../exploration/glb-viewport';

function model(index: number): CatalogModel {
  return {
    id: `model-${index}`,
    title: `Modelo ${index}`,
    topic: 'Ciencias naturales',
    source: 'Aula demo',
    license: 'CC BY 4.0',
    thumbnailUrl: `/assets/${index}.png`,
    assetUrl: `/assets/${index}.glb`,
    visitCount: index,
    capabilities: [],
  };
}

function response(items: CatalogModel[], total: number, offset = 0, limit = 8): ModelCatalogResponse {
  return { items, total, offset, limit };
}

describe('student model catalog', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideRouter(routes),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: '' },
      ],
    });
    TestBed.overrideComponent(GlbViewport, {
      set: { template: '<div data-testid="viewer-stub">Visor 3D</div>', styles: [] },
    });
    TestBed.inject(DemoProfileSession).enterAs('student');
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    sessionStorage.clear();
  });

  it('shows the plus tile and eight school models on the first 3x3 page', async () => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/alumno');
    http.expectOne((request) => request.url === '/api/v1/models' && request.params.get('offset') === '0' && request.params.get('limit') === '8')
      .flush(response(Array.from({ length: 8 }, (_, index) => model(index + 1)), 17));
    await harness.fixture.whenStable();
    harness.fixture.detectChanges();

    const page = harness.routeNativeElement as HTMLElement;
    expect(page.querySelector('[data-testid="upload-model"]')).not.toBeNull();
    expect(page.querySelectorAll('.model-card-button')).toHaveLength(8);
    expect(page.textContent).toContain('Página 1 de 2');
  });

  it('uses contiguous nine-model pages after the upload tile page', async () => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/alumno');
    http.expectOne((request) => request.params.get('offset') === '0').flush(response(Array.from({ length: 8 }, (_, index) => model(index + 1)), 17));
    await harness.fixture.whenStable();
    const page = harness.routeNativeElement as HTMLElement;
    page.querySelector<HTMLButtonElement>('.pagination button:last-child')?.click();
    await harness.fixture.whenStable();
    http.expectOne((request) => request.params.get('offset') === '8' && request.params.get('limit') === '9')
      .flush(response(Array.from({ length: 9 }, (_, index) => model(index + 9)), 17, 8, 9));
    await harness.fixture.whenStable();
    harness.fixture.detectChanges();

    expect((harness.routeNativeElement as HTMLElement).querySelector('[data-testid="upload-model"]')).toBeNull();
    expect((harness.routeNativeElement as HTMLElement).querySelectorAll('.model-card-button')).toHaveLength(9);
  });

  it('searches from the beginning and includes the search query in the API call', async () => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/alumno');
    http.expectOne((request) => request.params.get('offset') === '0').flush(response([], 0));
    await harness.fixture.whenStable();
    const search = (harness.routeNativeElement as HTMLElement).querySelector<HTMLInputElement>('input[matInput]')!;
    search.value = 'maceta';
    search.dispatchEvent(new Event('input'));
    http.expectOne((request) => request.params.get('search') === 'maceta' && request.params.get('offset') === '0')
      .flush(response([model(1)], 1));
    await harness.fixture.whenStable();
    harness.fixture.detectChanges();
    expect((harness.routeNativeElement as HTMLElement).textContent).toContain('Modelo 1');
  });

  it('opens a school model with one card click', async () => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/alumno');
    http.expectOne((request) => request.url === '/api/v1/models').flush(response([model(1)], 1));
    await harness.fixture.whenStable();
    (harness.routeNativeElement as HTMLElement).querySelector<HTMLButtonElement>('[data-testid="model-model-1"]')?.click();
    await harness.fixture.whenStable();
    http.expectOne('/api/v1/models/model-1').flush(model(1));
    await harness.fixture.whenStable();
    harness.fixture.detectChanges();

    expect(harness.routeNativeElement?.textContent).toContain('Modelo 1');
    expect((harness.routeNativeElement as HTMLElement).querySelector('[data-testid="viewer-stub"]')).not.toBeNull();
    http.expectOne('/api/v1/activity/model-visits').flush(null);
  });

  it('opens a selected local GLB in memory without sending it to the API', async () => {
    const originalCreate = URL.createObjectURL;
    const originalRevoke = URL.revokeObjectURL;
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: () => 'blob:temporary-model' });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: () => undefined });
    try {
      const harness = await RouterTestingHarness.create();
      await harness.navigateByUrl('/alumno');
      http.expectOne((request) => request.url === '/api/v1/models').flush(response([], 0));
      await harness.fixture.whenStable();
      const page = harness.routeNativeElement as HTMLElement;
      const input = page.querySelector<HTMLInputElement>('[data-testid="local-model-picker"]')!;
      const file = new File(['glb'], 'modelo-local.glb', { type: 'model/gltf-binary' });
      Object.defineProperty(input, 'files', { configurable: true, value: [file] });
      input.dispatchEvent(new Event('change'));
      await harness.fixture.whenStable();
      harness.fixture.detectChanges();

      expect(harness.routeNativeElement?.textContent).toContain('modelo-local.glb');
      expect(harness.routeNativeElement?.textContent).toContain('no se sube ni se guarda');
      expect(TestBed.inject(LocalModelLaunch).take()).toBeNull();
      http.expectNone((request) => request.method === 'POST' || request.method === 'PUT');
    } finally {
      Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: originalCreate });
      Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: originalRevoke });
    }
  });
});
