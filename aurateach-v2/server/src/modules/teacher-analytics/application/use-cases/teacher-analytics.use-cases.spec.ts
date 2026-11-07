import type { TeacherAnalyticsStorePort } from '../ports/outbound/teacher-analytics-store.port.js';
import type {
  AnalyticsQuery,
  DailyActivity,
  ModelUsage,
  StudentParticipation,
  StudentQuestionRecord,
  TeacherQuestionPage,
} from '../../domain/teacher-analytics.js';
import { ExportTeacherAnalyticsUseCase } from './export-teacher-analytics.use-case.js';
import { GetTeacherAnalyticsUseCase } from './get-teacher-analytics.use-case.js';
import { ListTeacherQuestionsUseCase } from './list-teacher-questions.use-case.js';

class InMemoryAnalyticsStore implements TeacherAnalyticsStorePort {
  readonly students: StudentParticipation[] = [
    { studentId: 10, displayName: 'Alumna activa', visitCount: 3, questionCount: 2, lastActivityAt: '2026-11-07T10:00:00.000Z' },
    { studentId: 11, displayName: 'Alumno sin actividad', visitCount: 0, questionCount: 0, lastActivityAt: null },
  ];
  readonly days: DailyActivity[] = [{ date: '2026-11-07', visits: 3, questions: 2 }];
  readonly models: ModelUsage[] = [{ modelId: 4, title: 'Guitarra', visitCount: 3, questionCount: 2 }];
  readonly questions: StudentQuestionRecord[] = [
    { questionId: 1, studentId: 10, displayName: 'Alumna activa', modelId: 4, modelTitle: 'Guitarra', questionText: '=IMPORTXML("malicious")', askedAt: '2026-11-07T10:00:00.000Z' },
  ];

  listStudentParticipation(_query: AnalyticsQuery): Promise<StudentParticipation[]> { return Promise.resolve(this.students); }
  listDailyActivity(_query: AnalyticsQuery): Promise<DailyActivity[]> { return Promise.resolve(this.days); }
  listModelUsage(_query: AnalyticsQuery): Promise<ModelUsage[]> { return Promise.resolve(this.models); }
  countVisits(_query: AnalyticsQuery): Promise<number> { return Promise.resolve(3); }
  countQuestions(_query: AnalyticsQuery): Promise<number> { return Promise.resolve(2); }
  listQuestions(_query: AnalyticsQuery, offset: number, limit: number): Promise<TeacherQuestionPage> {
    return Promise.resolve({ items: this.questions.slice(offset, offset + limit), offset, limit, total: this.questions.length });
  }
  listAllQuestions(_query: AnalyticsQuery): Promise<StudentQuestionRecord[]> { return Promise.resolve(this.questions); }
}

const query: AnalyticsQuery = { from: new Date('2026-11-01T00:00:00Z'), fromLabel: '2026-11-01', toExclusive: undefined, toLabel: null };

describe('teacher analytics use cases', () => {
  it('summarizes participation and includes students with no recent activity', async () => {
    const store = new InMemoryAnalyticsStore();
    const result = await new GetTeacherAnalyticsUseCase(store).execute(query);
    expect(result.totals).toEqual({ students: 2, activeStudents: 1, visits: 3, questions: 2 });
    expect(result.students[1]?.displayName).toBe('Alumno sin actividad');
    expect(result.dailyActivity).toEqual(store.days);
    expect(result.modelUsage).toEqual(store.models);
  });

  it('preserves offset and limit for question pagination', async () => {
    const store = new InMemoryAnalyticsStore();
    const result = await new ListTeacherQuestionsUseCase(store).execute(query, 0, 10);
    expect(result).toMatchObject({ offset: 0, limit: 10, total: 1 });
    expect(result.items[0]?.questionText).toContain('IMPORTXML');
  });

  it('exports participation and question records as escaped, spreadsheet-safe UTF-8 CSV', async () => {
    const csv = await new ExportTeacherAnalyticsUseCase(new InMemoryAnalyticsStore()).execute(query);
    expect(csv.charCodeAt(0)).toBe(0xfeff);
    expect(csv).toContain('participacion');
    expect(csv).toContain('pregunta');
    expect(csv).toContain("'=IMPORTXML(");
    expect(csv).toContain('"Alumna activa"');
  });
});
