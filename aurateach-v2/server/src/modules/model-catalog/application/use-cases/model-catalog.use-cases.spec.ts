import { GetSchoolModelAssetUseCase } from './get-school-model-asset.use-case.js';
import { GetSchoolModelUseCase } from './get-school-model.use-case.js';
import { ListSchoolModelsUseCase } from './list-school-models.use-case.js';
import type { ModelAssetStorePort } from '../ports/outbound/model-asset-store.port.js';
import type { ModelCatalogStorePort } from '../ports/outbound/model-catalog-store.port.js';
import type { SchoolModel } from '../../domain/school-model.js';

const schoolModel: SchoolModel = {
  id: 'lab-anatomia-corazon',
  title: 'Corazon',
  topic: 'Biología y ambiente',
  visitCount: 4,
  source: 'sample.glb',
  license: 'unknown',
};

describe('model catalogue use cases', () => {
  it('forwards the requested slice to the catalogue port', async () => {
    const page = { items: [schoolModel], offset: 8, limit: 9, total: 17 };
    const list = vi.fn().mockResolvedValue(page);
    const catalog: ModelCatalogStorePort = {
      list,
      findById: vi.fn(),
    };

    await expect(
      new ListSchoolModelsUseCase(catalog).execute({ search: 'cora', offset: 8, limit: 9 }),
    ).resolves.toEqual(page);
    expect(list).toHaveBeenCalledWith({ search: 'cora', offset: 8, limit: 9 });
  });

  it('returns null for an unknown school model', async () => {
    const catalog: ModelCatalogStorePort = {
      list: vi.fn(),
      findById: vi.fn().mockResolvedValue(null),
    };
    await expect(new GetSchoolModelUseCase(catalog).execute('unknown')).resolves.toBeNull();
  });

  it('does not resolve an asset for a model that is not in the catalogue', async () => {
    const catalog: ModelCatalogStorePort = {
      list: vi.fn(),
      findById: vi.fn().mockResolvedValue(null),
    };
    const resolveAsset = vi.fn();
    const assets: ModelAssetStorePort = { resolve: resolveAsset };
    await expect(
      new GetSchoolModelAssetUseCase(catalog, assets).execute('unknown', 'asset'),
    ).resolves.toBeNull();
    expect(resolveAsset).not.toHaveBeenCalled();
  });

  it('resolves a known model asset only after catalogue lookup', async () => {
    const catalog: ModelCatalogStorePort = {
      list: vi.fn(),
      findById: vi.fn().mockResolvedValue(schoolModel),
    };
    const asset = { path: '/safe/model.glb', contentType: 'model/gltf-binary' as const };
    const resolveAsset = vi.fn().mockResolvedValue(asset);
    const assets: ModelAssetStorePort = { resolve: resolveAsset };
    await expect(
      new GetSchoolModelAssetUseCase(catalog, assets).execute(schoolModel.id, 'asset'),
    ).resolves.toEqual(asset);
    expect(resolveAsset).toHaveBeenCalledWith(schoolModel.id, 'asset');
  });
});
