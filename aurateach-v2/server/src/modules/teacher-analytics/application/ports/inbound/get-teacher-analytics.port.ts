import type { AnalyticsQuery, TeacherAnalyticsSummary } from '../../../domain/teacher-analytics.js';

export interface GetTeacherAnalyticsPort {
  execute(query: AnalyticsQuery): Promise<TeacherAnalyticsSummary>;
}
