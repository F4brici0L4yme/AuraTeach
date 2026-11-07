import type { GetTeacherAnalyticsPort } from '../ports/inbound/get-teacher-analytics.port.js';
import type { TeacherAnalyticsStorePort } from '../ports/outbound/teacher-analytics-store.port.js';
import type { AnalyticsQuery, TeacherAnalyticsSummary } from '../../domain/teacher-analytics.js';

export class GetTeacherAnalyticsUseCase implements GetTeacherAnalyticsPort {
  constructor(private readonly store: TeacherAnalyticsStorePort) {}

  async execute(query: AnalyticsQuery): Promise<TeacherAnalyticsSummary> {
    const [students, dailyActivity, modelUsage, visits, questions] = await Promise.all([
      this.store.listStudentParticipation(query),
      this.store.listDailyActivity(query),
      this.store.listModelUsage(query),
      this.store.countVisits(query),
      this.store.countQuestions(query),
    ]);
    return {
      from: query.fromLabel,
      to: query.toLabel,
      totals: {
        students: students.length,
        activeStudents: students.filter((student) => student.visitCount + student.questionCount > 0).length,
        visits,
        questions,
      },
      students,
      dailyActivity,
      modelUsage,
    };
  }
}
