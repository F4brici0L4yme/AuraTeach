import { and, count, desc, eq, gte, lt, sql, type SQL } from 'drizzle-orm';
import type { TeacherAnalyticsStorePort } from '../../../application/ports/outbound/teacher-analytics-store.port.js';
import type {
  AnalyticsQuery,
  DailyActivity,
  ModelUsage,
  StudentParticipation,
  StudentQuestionRecord,
  TeacherQuestionPage,
} from '../../../domain/teacher-analytics.js';
import { enrollments, modelVisits, models, studentQuestions, users } from '../../../../../infrastructure/database/schema.js';
import type { AnalyticsDatabase } from './analytics-database.js';

function filtersFor(column: typeof modelVisits.visitedAt | typeof studentQuestions.askedAt, query: AnalyticsQuery): SQL[] {
  const filters: SQL[] = [];
  if (query.from) filters.push(gte(column, query.from));
  if (query.toExclusive) filters.push(lt(column, query.toExclusive));
  return filters;
}

function whereFor(column: typeof modelVisits.visitedAt | typeof studentQuestions.askedAt, query: AnalyticsQuery): SQL | undefined {
  const filters = filtersFor(column, query);
  return filters.length ? and(...filters) : undefined;
}

export class DrizzleTeacherAnalyticsStore implements TeacherAnalyticsStorePort {
  constructor(private readonly db: AnalyticsDatabase) {}

  async listStudentParticipation(query: AnalyticsQuery): Promise<StudentParticipation[]> {
    const [roster, visitRows, questionRows] = await Promise.all([
      this.db.selectDistinct({ id: users.id, displayName: users.displayName })
        .from(enrollments)
        .innerJoin(users, eq(users.id, enrollments.studentId))
        .where(eq(users.role, 'student')),
      this.db.select({ userId: modelVisits.userId, total: count(), latest: sql<Date>`max(${modelVisits.visitedAt})` })
        .from(modelVisits)
        .where(whereFor(modelVisits.visitedAt, query))
        .groupBy(modelVisits.userId),
      this.db.select({ userId: studentQuestions.userId, total: count(), latest: sql<Date>`max(${studentQuestions.askedAt})` })
        .from(studentQuestions)
        .where(whereFor(studentQuestions.askedAt, query))
        .groupBy(studentQuestions.userId),
    ]);
    const visitsByUser = new Map(visitRows.map((row) => [row.userId, { total: row.total, latest: row.latest }]));
    const questionsByUser = new Map(questionRows.map((row) => [row.userId, { total: row.total, latest: row.latest }]));
    return roster.map((student) => {
      const visits = visitsByUser.get(student.id);
      const questions = questionsByUser.get(student.id);
      // PostgreSQL may return `max(timestamp)` as an ISO string because it is a raw SQL expression.
      // Normalize both the driver Date value and the raw string before comparing them.
      const latest = [visits?.latest, questions?.latest]
        .filter((date): date is Date => Boolean(date))
        .map((date) => date instanceof Date ? date : new Date(date as unknown as string))
        .filter((date) => Number.isFinite(date.getTime()))
        .sort((left, right) => right.getTime() - left.getTime())[0];
      return {
        studentId: student.id,
        displayName: student.displayName,
        visitCount: visits?.total ?? 0,
        questionCount: questions?.total ?? 0,
        lastActivityAt: latest?.toISOString() ?? null,
      };
    }).sort((a, b) => (b.visitCount + b.questionCount) - (a.visitCount + a.questionCount) || a.displayName.localeCompare(b.displayName));
  }

  async listDailyActivity(query: AnalyticsQuery): Promise<DailyActivity[]> {
    const [visits, questions] = await Promise.all([
      this.db.select({ date: sql<string>`to_char(${modelVisits.visitedAt} at time zone 'UTC', 'YYYY-MM-DD')`, total: count() })
        .from(modelVisits)
        .where(whereFor(modelVisits.visitedAt, query))
        .groupBy(sql`to_char(${modelVisits.visitedAt} at time zone 'UTC', 'YYYY-MM-DD')`),
      this.db.select({ date: sql<string>`to_char(${studentQuestions.askedAt} at time zone 'UTC', 'YYYY-MM-DD')`, total: count() })
        .from(studentQuestions)
        .where(whereFor(studentQuestions.askedAt, query))
        .groupBy(sql`to_char(${studentQuestions.askedAt} at time zone 'UTC', 'YYYY-MM-DD')`),
    ]);
    const byDate = new Map<string, DailyActivity>();
    for (const row of visits) byDate.set(row.date, { date: row.date, visits: row.total, questions: 0 });
    for (const row of questions) {
      const current = byDate.get(row.date) ?? { date: row.date, visits: 0, questions: 0 };
      current.questions = row.total;
      byDate.set(row.date, current);
    }
    return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
  }

  async listModelUsage(query: AnalyticsQuery): Promise<ModelUsage[]> {
    const [visitRows, questionRows] = await Promise.all([
      this.db.select({ modelId: modelVisits.modelId, title: models.title, total: count() })
        .from(modelVisits)
        .innerJoin(models, eq(models.id, modelVisits.modelId))
        .where(whereFor(modelVisits.visitedAt, query))
        .groupBy(modelVisits.modelId, models.title),
      this.db.select({ modelId: studentQuestions.modelId, title: models.title, total: count() })
        .from(studentQuestions)
        .innerJoin(models, eq(models.id, studentQuestions.modelId))
        .where(whereFor(studentQuestions.askedAt, query))
        .groupBy(studentQuestions.modelId, models.title),
    ]);
    const byModel = new Map<number, ModelUsage>();
    for (const row of visitRows) byModel.set(row.modelId, { modelId: row.modelId, title: row.title, visitCount: row.total, questionCount: 0 });
    for (const row of questionRows) {
      const current = byModel.get(row.modelId) ?? { modelId: row.modelId, title: row.title, visitCount: 0, questionCount: 0 };
      current.questionCount = row.total;
      byModel.set(row.modelId, current);
    }
    return [...byModel.values()].sort((a, b) => b.visitCount + b.questionCount - a.visitCount - a.questionCount || a.title.localeCompare(b.title));
  }

  async countVisits(query: AnalyticsQuery): Promise<number> {
    const [row] = await this.db.select({ total: count() }).from(modelVisits).where(whereFor(modelVisits.visitedAt, query));
    return row?.total ?? 0;
  }

  async countQuestions(query: AnalyticsQuery): Promise<number> {
    const [row] = await this.db.select({ total: count() }).from(studentQuestions).where(whereFor(studentQuestions.askedAt, query));
    return row?.total ?? 0;
  }

  async listQuestions(query: AnalyticsQuery, offset: number, limit: number): Promise<TeacherQuestionPage> {
    const where = whereFor(studentQuestions.askedAt, query);
    const [totalRow] = await this.db.select({ total: count() }).from(studentQuestions).where(where);
    const rows = await this.selectQuestions(query).orderBy(desc(studentQuestions.askedAt), desc(studentQuestions.id)).limit(limit).offset(offset);
    return { items: rows.map((row) => this.toQuestionRecord(row)), offset, limit, total: totalRow?.total ?? 0 };
  }

  async listAllQuestions(query: AnalyticsQuery): Promise<StudentQuestionRecord[]> {
    const rows = await this.selectQuestions(query).orderBy(desc(studentQuestions.askedAt), desc(studentQuestions.id));
    return rows.map((row) => this.toQuestionRecord(row));
  }

  private selectQuestions(query: AnalyticsQuery) {
    return this.db.select({
      questionId: studentQuestions.id,
      studentId: users.id,
      displayName: users.displayName,
      modelId: models.id,
      modelTitle: models.title,
      questionText: studentQuestions.questionText,
      askedAt: studentQuestions.askedAt,
    })
      .from(studentQuestions)
      .innerJoin(users, eq(users.id, studentQuestions.userId))
      .innerJoin(models, eq(models.id, studentQuestions.modelId))
      .where(whereFor(studentQuestions.askedAt, query));
  }

  private toQuestionRecord(row: {
    questionId: number;
    studentId: number;
    displayName: string;
    modelId: number;
    modelTitle: string;
    questionText: string;
    askedAt: Date;
  }): StudentQuestionRecord {
    return {
      questionId: row.questionId,
      studentId: row.studentId,
      displayName: row.displayName,
      modelId: row.modelId,
      modelTitle: row.modelTitle,
      questionText: row.questionText,
      askedAt: row.askedAt.toISOString(),
    };
  }
}
