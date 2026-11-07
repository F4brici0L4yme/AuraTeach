import type { GetSchoolModelPort } from '../ports/inbound/get-school-model.port.js';
import type { SchoolModel } from '../../domain/school-model.js';
import type { ModelCatalogStorePort } from '../ports/outbound/model-catalog-store.port.js';

export class GetSchoolModelUseCase implements GetSchoolModelPort {
  constructor(private readonly catalog: ModelCatalogStorePort) {}

  execute(id: string): Promise<SchoolModel | null> {
    return this.catalog.findById(id);
  }
}
