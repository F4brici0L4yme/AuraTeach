import type {
  ListSchoolModelsPort,
  ListSchoolModelsQuery,
} from '../ports/inbound/list-school-models.port.js';
import type { ModelCatalogStorePort } from '../ports/outbound/model-catalog-store.port.js';

export class ListSchoolModelsUseCase implements ListSchoolModelsPort {
  constructor(private readonly catalog: ModelCatalogStorePort) {}

  execute(query: ListSchoolModelsQuery) {
    return this.catalog.list(query);
  }
}
