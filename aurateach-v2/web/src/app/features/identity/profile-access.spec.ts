import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { routes } from '../../app.routes';
import { API_BASE_URL } from '../../core/api/api-base-url';
import { DemoProfileSession } from './demo-profile-session';

describe('profile access flow', () => {
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
  });

  afterEach(() => sessionStorage.clear());

  it('shows the two profiles and keeps Enter disabled until one is selected', async () => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/');

    const page = harness.routeNativeElement as HTMLElement;
    expect(page.textContent).toContain('Docente');
    expect(page.textContent).toContain('Estudiante');
    expect(page.querySelector('[data-testid="enter"]')?.hasAttribute('disabled')).toBe(true);
  });

  it('routes the teacher profile to the teacher dashboard placeholder', async () => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/');
    const page = harness.routeNativeElement as HTMLElement;

    page.querySelector<HTMLElement>('[data-testid="teacher-profile"]')?.click();
    harness.fixture.detectChanges();
    expect(page.querySelector<HTMLButtonElement>('[data-testid="enter"]')?.disabled).toBe(false);
    page.querySelector<HTMLButtonElement>('[data-testid="enter"]')?.click();
    await harness.fixture.whenStable();
    harness.fixture.detectChanges();

    TestBed.inject(HttpTestingController).expectOne((request) => request.url === '/api/v1/teacher/analytics/summary').flush({
      from: null, to: null, students: [], totals: { students: 0, visits: 0, questions: 0, activeStudents: 0 }, dailyActivity: [], modelUsage: [],
    });
    TestBed.inject(HttpTestingController).expectOne((request) => request.url === '/api/v1/teacher/analytics/questions').flush({ items: [], offset: 0, limit: 25, total: 0 });
    await harness.fixture.whenStable();
    expect(harness.routeNativeElement?.textContent).toContain('Panel de aula');
    expect(TestBed.inject(DemoProfileSession).current()?.role).toBe('teacher');
  });

  it('routes the student profile to the model catalog', async () => {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/');
    const page = harness.routeNativeElement as HTMLElement;

    page.querySelector<HTMLElement>('[data-testid="student-profile"]')?.click();
    harness.fixture.detectChanges();
    expect(page.querySelector<HTMLButtonElement>('[data-testid="enter"]')?.disabled).toBe(false);
    page.querySelector<HTMLButtonElement>('[data-testid="enter"]')?.click();
    await harness.fixture.whenStable();
    TestBed.inject(HttpTestingController).expectOne((request) => request.url === '/api/v1/models')
      .flush({ items: [], offset: 0, limit: 8, total: 0 });
    await harness.fixture.whenStable();
    harness.fixture.detectChanges();

    expect(harness.routeNativeElement?.textContent).toContain('Biblioteca de modelos');
  });

  it('redirects an unauthenticated visitor to the profile selector', async () => {
    const harness = await RouterTestingHarness.create();

    await harness.navigateByUrl('/docente/dashboard');

    expect(harness.routeNativeElement?.textContent).toContain('Docente');
    expect(harness.routeNativeElement?.textContent).toContain('Estudiante');
  });

  it('does not allow the student profile to open the teacher dashboard', async () => {
    TestBed.inject(DemoProfileSession).enterAs('student');
    const harness = await RouterTestingHarness.create();

    await harness.navigateByUrl('/docente/dashboard');
    TestBed.inject(HttpTestingController).expectOne((request) => request.url === '/api/v1/models')
      .flush({ items: [], offset: 0, limit: 8, total: 0 });
    await harness.fixture.whenStable();

    expect(harness.routeNativeElement?.textContent).toContain('Biblioteca de modelos');
  });
});
