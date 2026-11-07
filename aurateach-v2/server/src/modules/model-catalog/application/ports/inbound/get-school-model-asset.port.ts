import type {
  ModelAssetVariant,
  ResolvedModelAsset,
} from '../../../domain/school-model.js';

export interface GetSchoolModelAssetPort {
  execute(id: string, variant: ModelAssetVariant): Promise<ResolvedModelAsset | null>;
}
