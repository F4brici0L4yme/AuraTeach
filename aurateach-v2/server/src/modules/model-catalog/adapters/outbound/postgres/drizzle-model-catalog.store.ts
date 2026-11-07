import { and, asc, count, desc, eq, ilike, isNotNull, or, sql } from 'drizzle-orm';
import type { ModelCatalogStorePort } from '../../../application/ports/outbound/model-catalog-store.port.js';
import type { ListSchoolModelsQuery } from '../../../application/ports/inbound/list-school-models.port.js';
import type { ModelCatalogPage, SchoolModel } from '../../../domain/school-model.js';
import { modelVisits, models } from '../../../../../infrastructure/database/schema.js';
import type { CatalogDatabase } from './model-catalog-database.js';

export class DrizzleModelCatalogStore implements ModelCatalogStorePort {
  constructor(private readonly db: CatalogDatabase) {}

  async list(query: ListSchoolModelsQuery): Promise<ModelCatalogPage> {
    const filters = [isNotNull(models.catalogKey)];
    const search = query.search?.trim();
    if (search) {
      const pattern = `%${search.replace(/[\\%_]/g, '\\$&')}%`;
      filters.push(or(ilike(models.title, pattern), ilike(models.topic, pattern))!);
    }
    const where = and(...filters);
    const [totalRow] = await this.db.select({ total: count() }).from(models).where(where);
    const visitCount = sql<number>`count(${modelVisits.id})::int`;
    const rows = await this.db
      .select({
        id: models.catalogKey,
        title: models.title,
        topic: models.topic,
        source: models.source,
        license: models.license,
        visitCount,
      })
      .from(models)
      .leftJoin(modelVisits, eq(modelVisits.modelId, models.id))
      .where(where)
      .groupBy(models.id)
      .orderBy(desc(visitCount), asc(models.title))
      .limit(query.limit)
      .offset(query.offset);

    return {
      items: rows.map((row) => this.toSchoolModel(row)),
      offset: query.offset,
      limit: query.limit,
      total: Number(totalRow?.total ?? 0),
    };
  }

  async findById(id: string): Promise<SchoolModel | null> {
    const visitCount = sql<number>`count(${modelVisits.id})::int`;
    const [row] = await this.db
      .select({
        id: models.catalogKey,
        title: models.title,
        topic: models.topic,
        source: models.source,
        license: models.license,
        visitCount,
      })
      .from(models)
      .leftJoin(modelVisits, eq(modelVisits.modelId, models.id))
      .where(and(eq(models.catalogKey, id), isNotNull(models.catalogKey)))
      .groupBy(models.id)
      .limit(1);
    return row ? this.toSchoolModel(row) : null;
  }

  private toSchoolModel(row: {
    id: string | null;
    title: string;
    topic: string;
    source: string | null;
    license: string | null;
    visitCount: number;
  }): SchoolModel {
    if (!row.id) throw new Error('A catalog model is missing its stable catalog id.');
    return {
      id: row.id,
      title: row.title,
      topic: row.topic,
      source: row.source ?? 'Unknown source',
      license: row.license ?? 'unknown',
      visitCount: row.visitCount,
    };
  }
}
