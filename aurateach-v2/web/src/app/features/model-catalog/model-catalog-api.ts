import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import type { paths } from '../../core/api/generated/api-types';
import { API_BASE_URL } from '../../core/api/api-base-url';

type ModelsOperation = paths['/models']['get'];
export type ModelCatalogResponse = ModelsOperation['responses'][200]['content']['application/json'];
export type CatalogModel = ModelCatalogResponse['items'][number];
export type ModelCatalogQuery = NonNullable<ModelsOperation['parameters']['query']>;

/** HTTP adapter for the generated catalog contract. */
@Injectable({ providedIn: 'root' })
export class ModelCatalogApi {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  list(query: ModelCatalogQuery) {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== '') {
        params = params.set(key, String(value));
      }
    }

    return this.http.get<ModelCatalogResponse>(`${this.apiBaseUrl}/api/v1/models`, { params });
  }

  get(id: string) {
    return this.http.get<CatalogModel>(`${this.apiBaseUrl}/api/v1/models/${encodeURIComponent(id)}`);
  }
}
