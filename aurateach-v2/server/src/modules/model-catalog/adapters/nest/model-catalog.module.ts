import { Module, OnApplicationShutdown, Inject } from '@nestjs/common';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { drizzle } from 'drizzle-orm/node-postgres';
import { Pool } from 'pg';
import * as schema from '../../../../infrastructure/database/schema.js';
import { ListSchoolModelsUseCase } from '../../application/use-cases/list-school-models.use-case.js';
import { GetSchoolModelUseCase } from '../../application/use-cases/get-school-model.use-case.js';
import { GetSchoolModelAssetUseCase } from '../../application/use-cases/get-school-model-asset.use-case.js';
import { ModelCatalogController } from '../inbound/http/model-catalog.controller.js';
import { DrizzleModelCatalogStore } from '../outbound/postgres/drizzle-model-catalog.store.js';
import { ManifestModelAssetStore } from '../outbound/filesystem/manifest-model-asset.store.js';
import type { CatalogDatabase } from '../outbound/postgres/model-catalog-database.js';
import {
  GET_SCHOOL_MODEL,
  GET_SCHOOL_MODEL_ASSET,
  LIST_SCHOOL_MODELS,
  MODEL_ASSET_STORE,
  MODEL_CATALOG_DATABASE,
  MODEL_CATALOG_STORE,
} from './model-catalog.tokens.js';

const MODEL_CATALOG_POOL = Symbol('MODEL_CATALOG_POOL');

function resolveCatalogAssetsDirectory(): string {
  const configured = process.env['AURATEACH_MODEL_CATALOG_DIR'];
  if (configured) return path.resolve(configured);
  const candidates = [
    path.resolve(process.cwd(), 'assets/model-catalog'),
    path.resolve(process.cwd(), 'server/assets/model-catalog'),
  ];
  return candidates.find((candidate) => existsSync(path.join(candidate, 'manifest.json'))) ?? candidates[0]!;
}

class CloseModelCatalogPool implements OnApplicationShutdown {
  constructor(@Inject(MODEL_CATALOG_POOL) private readonly pool: Pool) {}

  onApplicationShutdown(): Promise<void> {
    return this.pool.end();
  }
}

@Module({
  controllers: [ModelCatalogController],
  providers: [
    {
      provide: MODEL_CATALOG_POOL,
      useFactory: () => new Pool({ connectionString: process.env['DATABASE_URL'] }),
    },
    {
      provide: MODEL_CATALOG_DATABASE,
      inject: [MODEL_CATALOG_POOL],
      useFactory: (pool: Pool): CatalogDatabase => drizzle(pool, { schema }),
    },
    {
      provide: MODEL_CATALOG_STORE,
      inject: [MODEL_CATALOG_DATABASE],
      useFactory: (db: CatalogDatabase) => new DrizzleModelCatalogStore(db),
    },
    {
      provide: MODEL_ASSET_STORE,
      useFactory: () =>
        new ManifestModelAssetStore(resolveCatalogAssetsDirectory()),
    },
    {
      provide: LIST_SCHOOL_MODELS,
      inject: [MODEL_CATALOG_STORE],
      useFactory: (catalog: DrizzleModelCatalogStore) => new ListSchoolModelsUseCase(catalog),
    },
    {
      provide: GET_SCHOOL_MODEL,
      inject: [MODEL_CATALOG_STORE],
      useFactory: (catalog: DrizzleModelCatalogStore) => new GetSchoolModelUseCase(catalog),
    },
    {
      provide: GET_SCHOOL_MODEL_ASSET,
      inject: [MODEL_CATALOG_STORE, MODEL_ASSET_STORE],
      useFactory: (catalog: DrizzleModelCatalogStore, assets: ManifestModelAssetStore) =>
        new GetSchoolModelAssetUseCase(catalog, assets),
    },
    CloseModelCatalogPool,
  ],
})
export class ModelCatalogModule {}
