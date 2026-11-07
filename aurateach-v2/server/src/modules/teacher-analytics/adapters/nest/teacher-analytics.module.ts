import { Inject, Module, OnApplicationShutdown } from '@nestjs/common';
import { drizzle } from 'drizzle-orm/node-postgres';
import { Pool } from 'pg';
import * as schema from '../../../../infrastructure/database/schema.js';
import { GetTeacherAnalyticsUseCase } from '../../application/use-cases/get-teacher-analytics.use-case.js';
import { ListTeacherQuestionsUseCase } from '../../application/use-cases/list-teacher-questions.use-case.js';
import { ExportTeacherAnalyticsUseCase } from '../../application/use-cases/export-teacher-analytics.use-case.js';
import { DrizzleTeacherAnalyticsStore } from '../outbound/postgres/drizzle-teacher-analytics.store.js';
import { DrizzleDemoActivityStore } from '../outbound/postgres/drizzle-demo-activity.store.js';
import type { AnalyticsDatabase } from '../outbound/postgres/analytics-database.js';
import { TeacherAnalyticsController } from '../inbound/http/teacher-analytics.controller.js';
import { DemoActivityController } from '../inbound/http/demo-activity.controller.js';
import { RecordDemoModelVisitUseCase } from '../../application/use-cases/record-demo-model-visit.use-case.js';
import {
  EXPORT_TEACHER_ANALYTICS,
  DEMO_ACTIVITY_STORE,
  GET_TEACHER_ANALYTICS,
  LIST_TEACHER_QUESTIONS,
  TEACHER_ANALYTICS_DATABASE,
  TEACHER_ANALYTICS_POOL,
  TEACHER_ANALYTICS_STORE,
  RECORD_DEMO_MODEL_VISIT,
} from './teacher-analytics.tokens.js';

class CloseTeacherAnalyticsPool implements OnApplicationShutdown {
  constructor(@Inject(TEACHER_ANALYTICS_POOL) private readonly pool: Pool) {}
  onApplicationShutdown(): Promise<void> { return this.pool.end(); }
}

@Module({
  controllers: [TeacherAnalyticsController, DemoActivityController],
  providers: [
    { provide: TEACHER_ANALYTICS_POOL, useFactory: () => new Pool({ connectionString: process.env['DATABASE_URL'] }) },
    {
      provide: TEACHER_ANALYTICS_DATABASE,
      inject: [TEACHER_ANALYTICS_POOL],
      useFactory: (pool: Pool): AnalyticsDatabase => drizzle(pool, { schema }),
    },
    {
      provide: TEACHER_ANALYTICS_STORE,
      inject: [TEACHER_ANALYTICS_DATABASE],
      useFactory: (db: AnalyticsDatabase) => new DrizzleTeacherAnalyticsStore(db),
    },
    {
      provide: DEMO_ACTIVITY_STORE,
      inject: [TEACHER_ANALYTICS_DATABASE],
      useFactory: (db: AnalyticsDatabase) => new DrizzleDemoActivityStore(db),
    },
    {
      provide: GET_TEACHER_ANALYTICS,
      inject: [TEACHER_ANALYTICS_STORE],
      useFactory: (store: DrizzleTeacherAnalyticsStore) => new GetTeacherAnalyticsUseCase(store),
    },
    {
      provide: LIST_TEACHER_QUESTIONS,
      inject: [TEACHER_ANALYTICS_STORE],
      useFactory: (store: DrizzleTeacherAnalyticsStore) => new ListTeacherQuestionsUseCase(store),
    },
    {
      provide: EXPORT_TEACHER_ANALYTICS,
      inject: [TEACHER_ANALYTICS_STORE],
      useFactory: (store: DrizzleTeacherAnalyticsStore) => new ExportTeacherAnalyticsUseCase(store),
    },
    {
      provide: RECORD_DEMO_MODEL_VISIT,
      inject: [DEMO_ACTIVITY_STORE],
      useFactory: (store: DrizzleDemoActivityStore) => new RecordDemoModelVisitUseCase(store),
    },
    CloseTeacherAnalyticsPool,
  ],
})
export class TeacherAnalyticsModule {}
