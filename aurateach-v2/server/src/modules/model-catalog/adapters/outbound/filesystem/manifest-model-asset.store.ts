import { promises as fs } from 'node:fs';
import path from 'node:path';
import type { ModelAssetStorePort } from '../../../application/ports/outbound/model-asset-store.port.js';
import type {
  ModelAssetVariant,
  ResolvedModelAsset,
} from '../../../domain/school-model.js';
import { readCatalogManifest, type CatalogManifest } from '../../../../../infrastructure/model-catalog/catalog-manifest.js';

export class ManifestModelAssetStore implements ModelAssetStorePort {
  private manifestPromise: Promise<CatalogManifest> | undefined;

  constructor(private readonly assetsDirectory: string) {}

  async manifest(): Promise<CatalogManifest> {
    this.manifestPromise ??= readCatalogManifest(this.assetsDirectory);
    return this.manifestPromise;
  }

  async resolve(
    id: string,
    variant: ModelAssetVariant,
  ): Promise<ResolvedModelAsset | null> {
    let manifest: CatalogManifest;
    try {
      manifest = await this.manifest();
    } catch {
      return null;
    }
    const entry = manifest.models.find((model) => model.id === id && model.catalogKey === id);
    if (!entry) return null;

    const relative = variant === 'asset' ? entry.asset : entry.thumbnail;
    if (!relative || path.isAbsolute(relative) || relative.includes('\\')) return null;
    const segments = relative.split('/');
    if (segments.some((segment) => !segment || segment === '.' || segment === '..')) return null;
    if (variant === 'asset' && (segments[0] !== 'models' || !relative.endsWith('.glb'))) return null;
    if (variant === 'thumbnail' && (segments[0] !== 'thumbnails' || !relative.endsWith('.png'))) return null;

    try {
      const root = await fs.realpath(this.assetsDirectory);
      const resolved = await fs.realpath(path.resolve(root, ...segments));
      if (!resolved.startsWith(`${root}${path.sep}`)) return null;
      const stat = await fs.stat(resolved);
      if (!stat.isFile()) return null;
      return {
        path: resolved,
        contentType: variant === 'asset' ? 'model/gltf-binary' : 'image/png',
      };
    } catch {
      return null;
    }
  }
}
