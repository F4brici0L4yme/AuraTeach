import type { CheckHealthOutput } from '../../../application/ports/inbound/check-health.port.js';

export interface HealthHttpResponse {
  status: 'ok' | 'unavailable';
}

/** Maps application output to the public HTTP contract. */
export class HealthPresenter {
  static toHttp(output: CheckHealthOutput): HealthHttpResponse {
    return { status: output.isReady ? 'ok' : 'unavailable' };
  }
}
