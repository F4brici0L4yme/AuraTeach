import type { AnalyticsQuery } from '../../../domain/teacher-analytics.js';

export interface ExportTeacherAnalyticsPort {
  execute(query: AnalyticsQuery): Promise<string>;
}
