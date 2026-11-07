import type { RecordDemoModelVisitPort } from '../ports/inbound/record-demo-model-visit.port.js';
import type { DemoActivityStorePort } from '../ports/outbound/demo-activity-store.port.js';

export class RecordDemoModelVisitUseCase implements RecordDemoModelVisitPort {
  constructor(private readonly store: DemoActivityStorePort, private readonly createId: () => string = () => crypto.randomUUID()) {}

  execute(modelCatalogId: string): Promise<boolean> {
    return this.store.recordModelVisit(modelCatalogId, `live-visit-${this.createId()}`, new Date());
  }
}
