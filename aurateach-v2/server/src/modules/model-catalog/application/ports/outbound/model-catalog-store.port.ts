import type {
  ModelCatalogPage,
  SchoolModel,
} from '../../../domain/school-model.js';
import type { ListSchoolModelsQuery } from '../inbound/list-school-models.port.js';

/** Persistence port consumed by the catalogue use cases. */
export interface ModelCatalogStorePort {
  list(query: ListSchoolModelsQuery): Promise<ModelCatalogPage>;
  findById(id: string): Promise<SchoolModel | null>;
}
