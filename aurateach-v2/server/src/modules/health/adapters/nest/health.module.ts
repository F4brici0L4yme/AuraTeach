import { Module } from '@nestjs/common';
import { CHECK_HEALTH_PORT } from './health.tokens.js';
import type { CheckHealthPort } from '../../application/ports/inbound/check-health.port.js';
import { CheckHealthUseCase } from '../../application/use-cases/check-health.use-case.js';
import { HealthController } from '../inbound/http/health.controller.js';

/** Composition adapter: binds the inbound port to the framework-free use case. */
@Module({
  controllers: [HealthController],
  providers: [
    {
      provide: CHECK_HEALTH_PORT,
      useFactory: (): CheckHealthPort => new CheckHealthUseCase(),
    },
  ],
})
export class HealthModule {}
