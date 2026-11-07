import { promises as fs } from 'node:fs';
import path from 'node:path';

export interface CatalogManifestEntry {
  id: string;
  title: string;
  topic: string;
  asset: string;
  thumbnail: string;
  catalogKey: string;
  source: string;
  license: string;
}

export interface CatalogManifest {
  models: CatalogManifestEntry[];
}

const MODEL_ID_PATTERN = /^[a-z0-9]+(?:[-_][a-z0-9]+)*$/;

export async function readCatalogManifest(assetsDirectory: string): Promise<CatalogManifest> {
  const contents = await fs.readFile(path.join(assetsDirectory, 'manifest.json'), 'utf8');
  const manifest = JSON.parse(contents) as CatalogManifest;
  if (!Array.isArray(manifest.models)) throw new Error('Catalog manifest must include a models array.');

  const ids = new Set<string>();
  for (const model of manifest.models) {
    if (!MODEL_ID_PATTERN.test(model.id) || model.catalogKey !== model.id) {
      throw new Error(`Invalid stable catalog id in manifest: ${model.id}`);
    }
    if (ids.has(model.id)) throw new Error(`Duplicate catalog id in manifest: ${model.id}`);
    ids.add(model.id);
    for (const [variant, relative] of [['asset', model.asset], ['thumbnail', model.thumbnail]] as const) {
      const expectedDirectory = variant === 'asset' ? 'models' : 'thumbnails';
      const expectedExtension = variant === 'asset' ? '.glb' : '.png';
      if (
        typeof relative !== 'string' ||
        path.isAbsolute(relative) ||
        relative.includes('\\') ||
        !relative.startsWith(`${expectedDirectory}/`) ||
        !relative.endsWith(expectedExtension) ||
        relative.split('/').some((segment) => !segment || segment === '.' || segment === '..')
      ) {
        throw new Error(`Invalid ${variant} path in catalog manifest for ${model.id}.`);
      }
    }
    if (!model.title || !model.topic || !model.source || !model.license) {
      throw new Error(`Missing catalogue metadata for ${model.id}.`);
    }
  }
  return manifest;
}
