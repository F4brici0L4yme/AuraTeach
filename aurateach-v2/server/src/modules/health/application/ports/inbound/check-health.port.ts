export interface CheckHealthOutput {
  isReady: boolean;
}

/** Inbound port: the HTTP adapter drives this operation. */
export interface CheckHealthPort {
  execute(): CheckHealthOutput;
}
