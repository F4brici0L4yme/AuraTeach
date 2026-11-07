import {
  ArgumentsHost,
  Catch,
  ExceptionFilter,
  HttpException,
} from '@nestjs/common';
import type { Request, Response } from 'express';

@Catch(HttpException)
export class ModelCatalogProblemDetailsFilter implements ExceptionFilter<HttpException> {
  catch(exception: HttpException, host: ArgumentsHost): void {
    const http = host.switchToHttp();
    const response = http.getResponse<Response>();
    const request = http.getRequest<Request>();
    const status = exception.getStatus();
    const body = exception.getResponse();
    const bodyRecord = typeof body === 'object' && body !== null
      ? body as Record<string, unknown>
      : {};
    const rawMessage = bodyRecord['message'];
    const detail = Array.isArray(rawMessage)
      ? rawMessage.join('; ')
      : typeof rawMessage === 'string'
        ? rawMessage
        : typeof body === 'string'
          ? body
          : exception.message;
    const title = typeof bodyRecord['error'] === 'string'
      ? bodyRecord['error']
      : 'Request failed';

    response.status(status).type('application/problem+json').json({
      type: 'about:blank',
      title,
      status,
      detail,
      instance: request.originalUrl,
    });
  }
}
