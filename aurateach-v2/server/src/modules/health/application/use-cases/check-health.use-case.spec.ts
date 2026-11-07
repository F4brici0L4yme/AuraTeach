import { CheckHealthUseCase } from './check-health.use-case.js';

describe('CheckHealthUseCase', () => {
  it('reports the application as ready', () => {
    expect(new CheckHealthUseCase().execute()).toEqual({ isReady: true });
  });
});
