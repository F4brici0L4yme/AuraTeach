import type {
  CheckHealthOutput,
  CheckHealthPort,
} from '../ports/inbound/check-health.port.js';

/** Framework-free application operation used to verify the inbound boundary. */
export class CheckHealthUseCase implements CheckHealthPort {
  execute(): CheckHealthOutput {
    return { isReady: true };
  }
}
