import type { AnalyticsQuery, TeacherQuestionPage } from '../../../domain/teacher-analytics.js';

export interface ListTeacherQuestionsPort {
  execute(query: AnalyticsQuery, offset: number, limit: number): Promise<TeacherQuestionPage>;
}
