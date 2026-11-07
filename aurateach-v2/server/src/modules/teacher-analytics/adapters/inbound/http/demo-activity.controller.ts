import { BadRequestException, Body, Controller, HttpCode, Inject, Post } from '@nestjs/common';
import type { RecordDemoModelVisitPort } from '../../../application/ports/inbound/record-demo-model-visit.port.js';
import { RECORD_DEMO_MODEL_VISIT } from '../../nest/teacher-analytics.tokens.js';

@Controller('activity')
export class DemoActivityController {
  constructor(@Inject(RECORD_DEMO_MODEL_VISIT) private readonly recordVisit: RecordDemoModelVisitPort) {}

  @Post('model-visits')
  @HttpCode(204)
  async recordModelVisit(@Body() body: { modelId?: unknown }): Promise<void> {
    if (typeof body?.modelId !== 'string' || !body.modelId.trim() || body.modelId.length > 120) {
      throw new BadRequestException('modelId must be a non-empty catalog identifier.');
    }
    const recorded = await this.recordVisit.execute(body.modelId.trim());
    if (!recorded) throw new BadRequestException('Unknown modelId or demo student is not seeded.');
  }
}
