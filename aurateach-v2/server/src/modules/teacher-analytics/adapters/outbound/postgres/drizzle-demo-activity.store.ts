import { eq } from 'drizzle-orm';
import type { DemoActivityStorePort } from '../../../application/ports/outbound/demo-activity-store.port.js';
import { modelVisits, models, users } from '../../../../../infrastructure/database/schema.js';
import type { AnalyticsDatabase } from './analytics-database.js';

export class DrizzleDemoActivityStore implements DemoActivityStorePort {
  constructor(private readonly db: AnalyticsDatabase) {}

  async recordModelVisit(modelCatalogId: string, demoKey: string, visitedAt: Date): Promise<boolean> {
    const [student] = await this.db.select({ id: users.id }).from(users)
      .where(eq(users.demoKey, 'demo-student-01')).limit(1);
    const [model] = await this.db.select({ id: models.id }).from(models)
      .where(eq(models.catalogKey, modelCatalogId)).limit(1);
    if (!student || !model) return false;
    await this.db.insert(modelVisits).values({ userId: student.id, modelId: model.id, demoKey, visitedAt });
    return true;
  }
}
