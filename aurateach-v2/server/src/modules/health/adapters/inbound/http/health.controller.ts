import { Controller, Get, Inject } from '@nestjs/common';
import {
  type CheckHealthPort,
} from '../../../application/ports/inbound/check-health.port.js';
import { CHECK_HEALTH_PORT } from '../../nest/health.tokens.js';
import {
  HealthPresenter,
  type HealthHttpResponse,
} from './health.presenter.js';

@Controller('health')
export class HealthController {
  constructor(
    @Inject(CHECK_HEALTH_PORT)
    private readonly checkHealth: CheckHealthPort,
  ) {}

  @Get()
  getHealth(): HealthHttpResponse {
    return HealthPresenter.toHttp(this.checkHealth.execute());
  }
}
