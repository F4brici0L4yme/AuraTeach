import type { ModelCatalogPage } from '../../../domain/school-model.js';

export interface ListSchoolModelsQuery {
  search?: string;
  offset: number;
  limit: number;
}

export interface ListSchoolModelsPort {
  execute(query: ListSchoolModelsQuery): Promise<ModelCatalogPage>;
}
