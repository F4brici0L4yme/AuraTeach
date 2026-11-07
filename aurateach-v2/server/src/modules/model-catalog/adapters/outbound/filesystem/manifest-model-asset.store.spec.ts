import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { ManifestModelAssetStore } from './manifest-model-asset.store.js';

describe('ManifestModelAssetStore', () => {
  let directory: string;

  beforeEach(async () => {
    directory = await mkdtemp(path.join(os.tmpdir(), 'aurateach-catalog-assets-'));
    await mkdir(path.join(directory, 'models'));
    await mkdir(path.join(directory, 'thumbnails'));
    await writeFile(path.join(directory, 'models/corazon.glb'), 'glb');
    await writeFile(path.join(directory, 'thumbnails/corazon.png'), 'png');
    await writeFile(
      path.join(directory, 'manifest.json'),
      JSON.stringify({
        models: [
          {
            id: 'lab-anatomia-corazon',
            catalogKey: 'lab-anatomia-corazon',
            title: 'Corazon',
            topic: 'Biología y ambiente',
            asset: 'models/corazon.glb',
            thumbnail: 'thumbnails/corazon.png',
            source: 'sample.glb',
            license: 'unknown',
          },
        ],
      }),
    );
  });

  afterEach(async () => {
    await rm(directory, { recursive: true, force: true });
  });

  it('resolves allowlisted GLB and thumbnail files with their MIME types', async () => {
    const store = new ManifestModelAssetStore(directory);
    await expect(store.resolve('lab-anatomia-corazon', 'asset')).resolves.toMatchObject({
      path: path.join(directory, 'models/corazon.glb'),
      contentType: 'model/gltf-binary',
    });
    await expect(store.resolve('lab-anatomia-corazon', 'thumbnail')).resolves.toMatchObject({
      path: path.join(directory, 'thumbnails/corazon.png'),
      contentType: 'image/png',
    });
  });

  it('returns null for an unknown id or absent file', async () => {
    const store = new ManifestModelAssetStore(directory);
    await expect(store.resolve('other-model', 'asset')).resolves.toBeNull();
    await rm(path.join(directory, 'models/corazon.glb'));
    await expect(store.resolve('lab-anatomia-corazon', 'asset')).resolves.toBeNull();
  });

  it('rejects traversal paths from the manifest', async () => {
    await writeFile(
      path.join(directory, 'manifest.json'),
      JSON.stringify({
        models: [
          {
            id: 'lab-anatomia-corazon',
            catalogKey: 'lab-anatomia-corazon',
            title: 'Corazon',
            topic: 'Biología',
            asset: 'models/../../outside.glb',
            thumbnail: 'thumbnails/corazon.png',
            source: 'sample.glb',
            license: 'unknown',
          },
        ],
      }),
    );
    const store = new ManifestModelAssetStore(directory);
    await expect(store.resolve('lab-anatomia-corazon', 'asset')).resolves.toBeNull();
  });
});
