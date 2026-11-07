import type {
  AnalyticsQuery,
  StudentQuestionRecord,
  StudentParticipation,
  DailyActivity,
  ModelUsage,
  TeacherQuestionPage,
} from '../../../domain/teacher-analytics.js';

export interface TeacherAnalyticsStorePort {
  listStudentParticipation(query: AnalyticsQuery): Promise<StudentParticipation[]>;
  listDailyActivity(query: AnalyticsQuery): Promise<DailyActivity[]>;
  listModelUsage(query: AnalyticsQuery): Promise<ModelUsage[]>;
  countVisits(query: AnalyticsQuery): Promise<number>;
  countQuestions(query: AnalyticsQuery): Promise<number>;
  listQuestions(query: AnalyticsQuery, offset: number, limit: number): Promise<TeacherQuestionPage>;
  listAllQuestions(query: AnalyticsQuery): Promise<StudentQuestionRecord[]>;
}
