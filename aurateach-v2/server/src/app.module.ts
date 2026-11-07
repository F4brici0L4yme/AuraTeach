import { Module } from '@nestjs/common';
import { HealthModule } from './modules/health/adapters/nest/health.module.js';
import { ModelCatalogModule } from './modules/model-catalog/adapters/nest/model-catalog.module.js';
import { TutoringModule } from './modules/tutoring/adapters/nest/tutoring.module.js';
import { TeacherAnalyticsModule } from './modules/teacher-analytics/adapters/nest/teacher-analytics.module.js';

@Module({
  imports: [HealthModule, ModelCatalogModule, TutoringModule, TeacherAnalyticsModule],
})
export class AppModule {}
