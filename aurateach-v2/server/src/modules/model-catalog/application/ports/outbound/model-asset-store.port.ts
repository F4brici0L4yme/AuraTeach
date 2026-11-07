import type {
  ModelAssetVariant,
  ResolvedModelAsset,
} from '../../../domain/school-model.js';

/** Resolves only files declared by the trusted model-catalog manifest. */
export interface ModelAssetStorePort {
  resolve(id: string, variant: ModelAssetVariant): Promise<ResolvedModelAsset | null>;
}
