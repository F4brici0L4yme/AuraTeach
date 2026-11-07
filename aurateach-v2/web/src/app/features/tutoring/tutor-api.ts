import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { API_BASE_URL } from '../../core/api/api-base-url';
import type { components } from '../../core/api/generated/api-types';

export type TutorQuestion = components['schemas']['TutorQuestion'];
export type TutorAnswer = components['schemas']['TutorAnswer'];

@Injectable({ providedIn: 'root' })
export class TutorApi {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  ask(question: TutorQuestion) {
    return this.http.post<TutorAnswer>(`${this.apiBaseUrl}/api/v1/tutor/ask`, question);
  }
}
