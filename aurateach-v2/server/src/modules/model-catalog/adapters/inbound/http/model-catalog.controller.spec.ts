import { BadRequestException, NotFoundException, StreamableFile } from '@nestjs/common';
import type { GetSchoolModelPort } from '../../../application/ports/inbound/get-school-model.port.js';
import type { GetSchoolModelAssetPort } from '../../../application/ports/inbound/get-school-model-asset.port.js';
import type { ListSchoolModelsPort } from '../../../application/ports/inbound/list-school-models.port.js';
import { ModelCatalogController } from './model-catalog.controller.js';

const model = {
  id: 'lab-anatomia-corazon',
  title: 'Corazon',
  topic: 'Biología y ambiente',
  visitCount: 5,
  source: 'corazon.glb',
  license: 'unknown',
};

describe('ModelCatalogController', () => {
  const executeList = vi.fn();
  const executeGet = vi.fn();
  const executeAsset = vi.fn();
  const listModels: ListSchoolModelsPort = { execute: executeList };
  const getModel: GetSchoolModelPort = { execute: executeGet };
  const getAsset: GetSchoolModelAssetPort = {
    execute: executeAsset,
  };
  let controller: ModelCatalogController;

  beforeEach(() => {
    vi.clearAllMocks();
    executeList.mockResolvedValue({ items: [model], offset: 0, limit: 8, total: 1 });
    executeGet.mockResolvedValue(model);
    executeAsset.mockResolvedValue({ path: '/tmp/catalog/corazon.glb', contentType: 'model/gltf-binary' });
    controller = new ModelCatalogController(listModels, getModel, getAsset);
  });

  it('uses safe defaults and includes URLs in a catalogue slice', async () => {
    await expect(controller.list()).resolves.toEqual({
      items: [{
        ...model,
        capabilities: [],
        assetUrl: '/api/v1/models/lab-anatomia-corazon/asset',
        thumbnailUrl: '/api/v1/models/lab-anatomia-corazon/thumbnail',
      }],
      offset: 0,
      limit: 8,
      total: 1,
    });
    expect(executeList).toHaveBeenCalledWith({ offset: 0, limit: 9 });
  });

  it('accepts offset slices and trimmed search strings', async () => {
    await controller.list('  cora  ', '8', '9');
    expect(executeList).toHaveBeenCalledWith({ search: 'cora', offset: 8, limit: 9 });
  });

  it('rejects invalid bounds and overlong search strings', async () => {
    await expect(controller.list(undefined, '-1', '9')).rejects.toBeInstanceOf(BadRequestException);
    await expect(controller.list(undefined, '0', '25')).rejects.toBeInstanceOf(BadRequestException);
    await expect(controller.list('a'.repeat(101))).rejects.toBeInstanceOf(BadRequestException);
  });

  it('returns model details directly and 404s for missing models', async () => {
    await expect(controller.get(model.id)).resolves.toMatchObject({
      id: model.id,
      assetUrl: `/api/v1/models/${model.id}/asset`,
    });
    executeGet.mockResolvedValueOnce(null);
    await expect(controller.get(model.id)).rejects.toBeInstanceOf(NotFoundException);
  });

  it('rejects malformed ids and streams a known asset', async () => {
    await expect(controller.asset('../outside')).rejects.toBeInstanceOf(BadRequestException);
    await expect(controller.asset(model.id)).resolves.toBeInstanceOf(StreamableFile);
    expect(executeAsset).toHaveBeenCalledWith(model.id, 'asset');
  });
});
