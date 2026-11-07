import { HttpClient } from '@angular/common/http';
import { inject, Service } from '@angular/core';
import type { paths } from './generated/api-types';
import { API_BASE_URL } from './api-base-url';

type HealthResponse =
  paths['/health']['get']['responses'][200]['content']['application/json'];

/** HTTP adapter for the versioned health endpoint. */
@Service()
export class HealthApi {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  check() {
    return this.http.get<HealthResponse>(`${this.apiBaseUrl}/health`);
  }
}
