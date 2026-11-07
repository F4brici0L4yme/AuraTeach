import type { ExportTeacherAnalyticsPort } from '../ports/inbound/export-teacher-analytics.port.js';
import type { TeacherAnalyticsStorePort } from '../ports/outbound/teacher-analytics-store.port.js';
import type { AnalyticsQuery } from '../../domain/teacher-analytics.js';

function csvCell(value: string | number | null): string {
  let text = value === null ? '' : String(value);
  if (/^[\u0000-\u0020]*[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

export class ExportTeacherAnalyticsUseCase implements ExportTeacherAnalyticsPort {
  constructor(private readonly store: TeacherAnalyticsStorePort) {}

  async execute(query: AnalyticsQuery): Promise<string> {
    const [students, questions] = await Promise.all([
      this.store.listStudentParticipation(query),
      this.store.listAllQuestions(query),
    ]);
    const rows = [
      ['tipo', 'fecha', 'alumno', 'modelo', 'visitas', 'preguntas', 'ultima_actividad', 'pregunta'],
      ...students.map((student) => [
        'participacion', '', student.displayName, '', student.visitCount, student.questionCount, student.lastActivityAt ?? '', '',
      ]),
      ...questions.map((question) => [
        'pregunta', question.askedAt, question.displayName, question.modelTitle, '', '', '', question.questionText,
      ]),
    ];
    return `\uFEFF${rows.map((row) => row.map(csvCell).join(',')).join('\r\n')}\r\n`;
  }
}
