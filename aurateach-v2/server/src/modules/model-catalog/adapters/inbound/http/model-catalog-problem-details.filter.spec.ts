import { ArgumentsHost, NotFoundException } from '@nestjs/common';
import { ModelCatalogProblemDetailsFilter } from './model-catalog-problem-details.filter.js';

describe('ModelCatalogProblemDetailsFilter', () => {
  it('maps Nest exceptions to the documented problem-details shape', () => {
    const response = {
      status: vi.fn().mockReturnThis(),
      type: vi.fn().mockReturnThis(),
      json: vi.fn(),
    };
    const request = { originalUrl: '/api/v1/models/missing' };
    const host = {
      switchToHttp: () => ({
        getResponse: () => response,
        getRequest: () => request,
      }),
    } as unknown as ArgumentsHost;

    new ModelCatalogProblemDetailsFilter().catch(
      new NotFoundException('School model not found.'),
      host,
    );

    expect(response.status).toHaveBeenCalledWith(404);
    expect(response.type).toHaveBeenCalledWith('application/problem+json');
    expect(response.json).toHaveBeenCalledWith({
      type: 'about:blank',
      title: 'Not Found',
      status: 404,
      detail: 'School model not found.',
      instance: '/api/v1/models/missing',
    });
  });
});
