import type { ListTeacherQuestionsPort } from '../ports/inbound/list-teacher-questions.port.js';
import type { TeacherAnalyticsStorePort } from '../ports/outbound/teacher-analytics-store.port.js';
import type { AnalyticsQuery, TeacherQuestionPage } from '../../domain/teacher-analytics.js';

export class ListTeacherQuestionsUseCase implements ListTeacherQuestionsPort {
  constructor(private readonly store: TeacherAnalyticsStorePort) {}

  execute(query: AnalyticsQuery, offset: number, limit: number): Promise<TeacherQuestionPage> {
    return this.store.listQuestions(query, offset, limit);
  }
}
