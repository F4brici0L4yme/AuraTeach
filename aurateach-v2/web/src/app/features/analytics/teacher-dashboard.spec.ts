import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TeacherAnalyticsApi, type AnalyticsSummary, type QuestionsPage } from './teacher-analytics-api';
import { TeacherDashboard } from './teacher-dashboard';

const summaryFixture: AnalyticsSummary = {
  from: '2026-11-01',
  to: '2026-11-07',
  students: [
    { studentId: 1, displayName: 'Estudiante A', visitCount: 0, questionCount: 0 },
    { studentId: 2, displayName: 'Estudiante B', visitCount: 5, questionCount: 2, lastActivityAt: '2026-11-06T14:00:00Z' },
  ],
  totals: { students: 2, activeStudents: 1, visits: 5, questions: 2 },
  dailyActivity: [{ date: '2026-11-06', visits: 5, questions: 2 }],
  modelUsage: [{ modelId: 7, title: 'Maceta escolar', visitCount: 5, questionCount: 2 }],
};

function questionPage(offset: number, total: number): QuestionsPage {
  const count = Math.min(25, Math.max(0, total - offset));
  return {
    offset,
    limit: 25,
    total,
    items: Array.from({ length: count }, (_, index) => ({
      questionId: offset + index + 1,
      studentId: 1,
      displayName: `Estudiante ${offset + index + 1}`,
      modelId: 7,
      modelTitle: 'Maceta escolar',
      questionText: `Pregunta ${offset + index + 1}`,
      askedAt: '2026-11-06T14:00:00Z',
    })),
  };
}

describe('TeacherDashboard', () => {
  let fixture: ComponentFixture<TeacherDashboard>;
  let api: {
    summary: ReturnType<typeof vi.fn>;
    questions: ReturnType<typeof vi.fn>;
    exportCsv: ReturnType<typeof vi.fn>;
  };
  let originalCreateObjectUrl: PropertyDescriptor | undefined;
  let originalRevokeObjectUrl: PropertyDescriptor | undefined;

  beforeEach(() => {
    api = {
      summary: vi.fn(() => of(summaryFixture)),
      questions: vi.fn((_filters, offset = 0) => of(questionPage(offset, 30))),
      exportCsv: vi.fn(() => of(new Blob(['pregunta,estudiante\n']))),
    };
    TestBed.configureTestingModule({
      imports: [TeacherDashboard],
      providers: [provideRouter([]), { provide: TeacherAnalyticsApi, useValue: api }],
    });
    fixture = TestBed.createComponent(TeacherDashboard);
    fixture.detectChanges();
  });

  afterEach(() => {
    fixture.destroy();
    restoreProperty(URL, 'createObjectURL', originalCreateObjectUrl);
    restoreProperty(URL, 'revokeObjectURL', originalRevokeObjectUrl);
    vi.restoreAllMocks();
  });

  it('passes the selected date range to the summary request', () => {
    const component = fixture.componentInstance as unknown as { from: string; to: string };
    component.from = '2026-10-10';
    component.to = '2026-10-20';
    fixture.nativeElement.querySelector('.toolbar button')!.click();
    fixture.detectChanges();

    expect(api.summary).toHaveBeenLastCalledWith({ from: '2026-10-10', to: '2026-10-20' });
  });

  it('renders aggregate participation and flags students who need support', () => {
    const page = fixture.nativeElement as HTMLElement;
    expect(page.querySelector('.kpi.primary strong')?.textContent).toContain('1');
    expect(page.querySelector('.kpi.attention strong')?.textContent).toContain('1');
    expect(page.textContent).toContain('Estudiante A');
    expect(page.textContent).toContain('Revisar y acompañar');
    expect(page.textContent).toContain('Participando');
    expect(page.textContent).toContain('Maceta escolar');
    expect(page.textContent).toContain('Pregunta 1');
  });

  it('keeps quiet dates visible in the daily activity chart', () => {
    const days = fixture.nativeElement.querySelectorAll('.day-column');
    expect(days).toHaveLength(7);
    expect(days[0].getAttribute('title')).toContain('2026-11-01: 0 visitas, 0 preguntas');
    expect(days[5].getAttribute('title')).toContain('2026-11-06: 5 visitas, 2 preguntas');
  });

  it('loads the next page of questions and updates the visible range', () => {
    fixture.nativeElement.querySelector('.pager button:last-child')!.click();
    fixture.detectChanges();

    expect(api.questions).toHaveBeenLastCalledWith(expect.objectContaining({ from: expect.any(String), to: expect.any(String) }), 25, 25);
    expect(fixture.nativeElement.querySelector('.pager')?.textContent).toContain('26–30 de 30');
    expect(fixture.nativeElement.textContent).toContain('Pregunta 26');
    expect(fixture.nativeElement.textContent).not.toContain('Pregunta 1</td>');
  });

  it('downloads the CSV response using the expected filename and revokes its object URL', () => {
    vi.useFakeTimers();
    const createObjectURL = vi.fn(() => 'blob:aurateach-report');
    const revokeObjectURL = vi.fn();
    originalCreateObjectUrl = Object.getOwnPropertyDescriptor(URL, 'createObjectURL');
    originalRevokeObjectUrl = Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL');
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL });
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);

    fixture.nativeElement.querySelector('.toolbar button:nth-of-type(2)')!.click();
    fixture.detectChanges();
    const clickedAnchor = anchorClick.mock.instances[0] as HTMLAnchorElement;

    expect(api.exportCsv).toHaveBeenCalledWith(expect.objectContaining({ from: expect.any(String), to: expect.any(String) }));
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(clickedAnchor.download).toBe('aurateach-reporte-aula.csv');
    expect(clickedAnchor.href).toBe('blob:aurateach-report');
    expect(anchorClick).toHaveBeenCalledOnce();
    vi.advanceTimersByTime(1000);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:aurateach-report');
    vi.useRealTimers();
  });
});

function restoreProperty(target: object, key: string, descriptor: PropertyDescriptor | undefined): void {
  if (descriptor) Object.defineProperty(target, key, descriptor);
  else Reflect.deleteProperty(target, key);
}
