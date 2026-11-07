import type {
  ModelCatalogPage,
  SchoolModel,
} from '../../../domain/school-model.js';

export interface SchoolModelHttpResponse extends SchoolModel {
  assetUrl: string;
  thumbnailUrl: string;
  capabilities: Array<'semantic-parts' | 'disassembly'>;
}

export class ModelCatalogPresenter {
  static toModel(model: SchoolModel): SchoolModelHttpResponse {
    const base = `/api/v1/models/${encodeURIComponent(model.id)}`;
    return {
      ...model,
      assetUrl: `${base}/asset`,
      thumbnailUrl: `${base}/thumbnail`,
      capabilities: model.id === 'guitarra-acustica' ? ['semantic-parts', 'disassembly'] : [],
    };
  }

  static toPage(page: ModelCatalogPage) {
    return {
      ...page,
      items: page.items.map((item) => ModelCatalogPresenter.toModel(item)),
    };
  }
}
