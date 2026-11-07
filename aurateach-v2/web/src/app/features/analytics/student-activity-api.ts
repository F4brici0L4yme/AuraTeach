import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { API_BASE_URL } from '../../core/api/api-base-url';

@Injectable({ providedIn: 'root' })
export class StudentActivityApi {
  private readonly http = inject(HttpClient);
  private readonly base = inject(API_BASE_URL);

  recordModelVisit(modelId: string) {
    return this.http.post<void>(`${this.base}/api/v1/activity/model-visits`, { modelId });
  }
}
