/** A school-owned model prepared for the educational catalogue. */
export interface SchoolModel {
  id: string;
  title: string;
  topic: string;
  visitCount: number;
  source: string;
  license: string;
}

export interface ModelCatalogPage {
  items: SchoolModel[];
  offset: number;
  limit: number;
  total: number;
}

export type ModelAssetVariant = 'asset' | 'thumbnail';

export interface ResolvedModelAsset {
  path: string;
  contentType: 'model/gltf-binary' | 'image/png';
}
