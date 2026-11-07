import { BadRequestException, Controller, Get, Header, Inject, Query } from '@nestjs/common';
import type { AnalyticsQuery } from '../../../domain/teacher-analytics.js';
import type { GetTeacherAnalyticsPort } from '../../../application/ports/inbound/get-teacher-analytics.port.js';
import type { ListTeacherQuestionsPort } from '../../../application/ports/inbound/list-teacher-questions.port.js';
import type { ExportTeacherAnalyticsPort } from '../../../application/ports/inbound/export-teacher-analytics.port.js';
import { EXPORT_TEACHER_ANALYTICS, GET_TEACHER_ANALYTICS, LIST_TEACHER_QUESTIONS } from '../../nest/teacher-analytics.tokens.js';

function parseDateRange(from?: string, to?: string): AnalyticsQuery {
  const parse = (value: string | undefined, name: string): Date | undefined => {
    if (value === undefined || value === '') return undefined;
    const isDate = /^\d{4}-\d{2}-\d{2}$/.test(value);
    const isTimestamp = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?(?:Z|[+-]\d{2}:\d{2})$/.test(value);
    if (!isDate && !isTimestamp) throw new BadRequestException(`${name} must be an ISO date or timestamp.`);
    const date = new Date(value);
    if (!Number.isFinite(date.getTime()) || (isDate && date.toISOString().slice(0, 10) !== value)) {
      throw new BadRequestException(`${name} must be a valid ISO date or timestamp.`);
    }
    return date;
  };
  const parsedFrom = parse(from, 'from');
  const parsedTo = parse(to, 'to');
  if (parsedFrom && parsedTo && parsedFrom > parsedTo) {
    throw new BadRequestException('from must be earlier than or equal to to.');
  }
  const toExclusive = parsedTo
    ? new Date(parsedTo.getTime() + (to && /^\d{4}-\d{2}-\d{2}$/.test(to) ? 86_400_000 : 1))
    : undefined;
  return {
    from: parsedFrom,
    toExclusive,
    fromLabel: parsedFrom?.toISOString().slice(0, 10) ?? null,
    toLabel: parsedTo?.toISOString().slice(0, 10) ?? null,
  };
}

function parseInteger(value: string | undefined, fallback: number, name: string, minimum: number, maximum: number): number {
  if (value === undefined || value === '') return fallback;
  if (!/^\d+$/.test(value)) throw new BadRequestException(`${name} must be an integer.`);
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new BadRequestException(`${name} must be between ${minimum} and ${maximum}.`);
  }
  return parsed;
}

@Controller('teacher/analytics')
export class TeacherAnalyticsController {
  constructor(
    @Inject(GET_TEACHER_ANALYTICS) private readonly getSummary: GetTeacherAnalyticsPort,
    @Inject(LIST_TEACHER_QUESTIONS) private readonly listQuestions: ListTeacherQuestionsPort,
    @Inject(EXPORT_TEACHER_ANALYTICS) private readonly exportAnalytics: ExportTeacherAnalyticsPort,
  ) {}

  @Get('summary')
  getAnalyticsSummary(@Query('from') from?: string, @Query('to') to?: string) {
    return this.getSummary.execute(parseDateRange(from, to));
  }

  @Get('questions')
  getQuestions(
    @Query('from') from?: string,
    @Query('to') to?: string,
    @Query('offset') offset?: string,
    @Query('limit') limit?: string,
  ) {
    return this.listQuestions.execute(
      parseDateRange(from, to),
      parseInteger(offset, 0, 'offset', 0, 100_000),
      parseInteger(limit, 25, 'limit', 1, 100),
    );
  }

  @Get('export.csv')
  @Header('Content-Type', 'text/csv; charset=utf-8')
  @Header('Content-Disposition', 'attachment; filename="aurateach-analytics.csv"')
  exportCsv(@Query('from') from?: string, @Query('to') to?: string): Promise<string> {
    return this.exportAnalytics.execute(parseDateRange(from, to));
  }
}
