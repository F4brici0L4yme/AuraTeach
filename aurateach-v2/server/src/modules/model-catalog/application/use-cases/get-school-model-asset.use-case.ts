import type { GetSchoolModelAssetPort } from '../ports/inbound/get-school-model-asset.port.js';
import type {
  ModelAssetVariant,
  ResolvedModelAsset,
} from '../../domain/school-model.js';
import type { ModelAssetStorePort } from '../ports/outbound/model-asset-store.port.js';
import type { ModelCatalogStorePort } from '../ports/outbound/model-catalog-store.port.js';

export class GetSchoolModelAssetUseCase implements GetSchoolModelAssetPort {
  constructor(
    private readonly catalog: ModelCatalogStorePort,
    private readonly assets: ModelAssetStorePort,
  ) {}

  async execute(
    id: string,
    variant: ModelAssetVariant,
  ): Promise<ResolvedModelAsset | null> {
    if (!(await this.catalog.findById(id))) return null;
    return this.assets.resolve(id, variant);
  }
}
