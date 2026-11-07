import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { API_BASE_URL } from '../../core/api/api-base-url';
import type { paths } from '../../core/api/generated/api-types';

export type AnalyticsSummary = paths['/teacher/analytics/summary']['get']['responses'][200]['content']['application/json'];
export type QuestionsPage = paths['/teacher/analytics/questions']['get']['responses'][200]['content']['application/json'];
export interface AnalyticsFilters { from?: string; to?: string }

@Injectable({ providedIn: 'root' })
export class TeacherAnalyticsApi {
  private readonly http = inject(HttpClient);
  private readonly base = inject(API_BASE_URL);

  summary(filters: AnalyticsFilters) {
    return this.http.get<AnalyticsSummary>(`${this.base}/api/v1/teacher/analytics/summary`, { params: this.params({ ...filters }) });
  }

  questions(filters: AnalyticsFilters, offset = 0, limit = 25) {
    return this.http.get<QuestionsPage>(`${this.base}/api/v1/teacher/analytics/questions`, {
      params: this.params({ ...filters, offset, limit }),
    });
  }

  exportCsv(filters: AnalyticsFilters) {
    return this.http.get(`${this.base}/api/v1/teacher/analytics/export.csv`, {
      params: this.params({ ...filters }), responseType: 'blob',
    });
  }

  private params(values: Record<string, string | number | undefined>) {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(values)) if (value !== undefined) params = params.set(key, String(value));
    return params;
  }
}
