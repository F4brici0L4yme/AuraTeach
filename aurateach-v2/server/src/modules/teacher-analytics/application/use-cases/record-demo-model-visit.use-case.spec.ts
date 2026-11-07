import type { DemoActivityStorePort } from '../ports/outbound/demo-activity-store.port.js';
import { RecordDemoModelVisitUseCase } from './record-demo-model-visit.use-case.js';

describe('RecordDemoModelVisitUseCase', () => {
  it('records the stable model id for the demo student with a unique event key', async () => {
    const captured: unknown[][] = [];
    const store: DemoActivityStorePort = {
      recordModelVisit: async (...args) => { captured.push(args); return true; },
    };
    const useCase = new RecordDemoModelVisitUseCase(store, () => 'fixed-id');
    await expect(useCase.execute('guitar')).resolves.toBe(true);
    expect(captured[0]?.[0]).toBe('guitar');
    expect(captured[0]?.[1]).toBe('live-visit-fixed-id');
    expect(captured[0]?.[2]).toBeInstanceOf(Date);
  });

  it('returns false when the model or demo student cannot be resolved', async () => {
    const store: DemoActivityStorePort = { recordModelVisit: async () => false };
    await expect(new RecordDemoModelVisitUseCase(store).execute('unknown')).resolves.toBe(false);
  });
});
