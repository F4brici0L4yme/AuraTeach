import dotenv from 'dotenv';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { and, count, eq, inArray } from 'drizzle-orm';
import { drizzle } from 'drizzle-orm/node-postgres';
import { Pool } from 'pg';
import { classrooms, enrollments, modelVisits, models, studentQuestions, users } from '../../src/infrastructure/database/schema.js';

const here = path.dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: path.resolve(here, '../../../.env') });
const databaseUrl = process.env['DATABASE_URL'];
if (!databaseUrl) throw new Error('DATABASE_URL is required. Copy .env.example to .env first.');

const pool = new Pool({ connectionString: databaseUrl });
const db = drizzle(pool);
const students = Array.from({ length: 8 }, (_, i) => ({
  key: `smoke-analytics-student-${String(i + 1).padStart(2, '0')}`,
  name: `Participante demo ${String(i + 1).padStart(2, '0')}`,
}));
const questions = [
  '¿Qué evidencia permite reconocer esta parte del modelo?',
  '¿Cómo cambiaría el resultado si variamos el material?',
  '¿Qué relación observas entre la forma y su función?',
  '¿Qué dato adicional ayudaría a comprobar esta idea?',
  '¿Qué semejanza tiene este objeto con uno de nuestro entorno?',
  '¿Qué detalle te gustaría observar con más precisión?',
  '¿Qué pregunta nueva surge al comparar estos modelos?',
  '¿Qué componente parece cumplir una función estructural?',
  '¿Cómo se podría probar esta explicación en un experimento?',
  '¿Qué causa podría explicar la diferencia que observamos?',
  '¿Qué material alternativo podríamos investigar?',
  '¿Qué parte del modelo conecta con un tema ambiental?',
];

async function seed(): Promise<void> {
  await db.transaction(async (tx) => {
    const [teacher] = await tx.insert(users).values({
      role: 'teacher', displayName: 'Docente smoke', demoKey: 'smoke-analytics-teacher',
    }).onConflictDoUpdate({
      target: users.demoKey,
      set: { role: 'teacher', displayName: 'Docente smoke' },
    }).returning({ id: users.id });

    const studentRows: Array<(typeof students)[number] & { id: number }> = [];
    for (const student of students) {
      const [row] = await tx.insert(users).values({
        role: 'student', displayName: student.name, demoKey: student.key,
      }).onConflictDoUpdate({
        target: users.demoKey,
        set: { role: 'student', displayName: student.name },
      }).returning({ id: users.id });
      studentRows.push({ ...student, id: row!.id });
    }

    const [classroom] = await tx.insert(classrooms).values({
      teacherId: teacher!.id, name: 'Aula sintética de analítica', demoKey: 'smoke-analytics-classroom',
    }).onConflictDoUpdate({
      target: classrooms.demoKey,
      set: { teacherId: teacher!.id, name: 'Aula sintética de analítica' },
    }).returning({ id: classrooms.id });

    await tx.insert(enrollments).values(studentRows.map((student) => ({
      classroomId: classroom!.id, studentId: student.id,
    }))).onConflictDoNothing();

    const catalogModels = await tx.select({ id: models.id }).from(models)
      .where(inArray(models.catalogKey, ['maceta', 'lapicero', 'guitarra-acustica']));
    if (catalogModels.length < 2) throw new Error('Seed the school model catalog before running the dashboard smoke.');

    const now = Date.now();
    const visits = Array.from({ length: 24 }, (_, index) => ({
      userId: studentRows[index % 6]!.id,
      modelId: catalogModels[index % catalogModels.length]!.id,
      demoKey: `smoke-analytics-visit-${String(index + 1).padStart(3, '0')}`,
      visitedAt: new Date(now - [0, 1, 2, 3, 5, 8, 12, 18, 24, 31][index % 10]! * 86_400_000 - (index % 8) * 3_600_000),
    }));
    for (const visit of visits) {
      await tx.insert(modelVisits).values(visit).onConflictDoUpdate({
        target: modelVisits.demoKey,
        set: { userId: visit.userId, modelId: visit.modelId, visitedAt: visit.visitedAt },
      });
    }

    const questionEvents = Array.from({ length: 16 }, (_, index) => ({
      userId: studentRows[index % 6]!.id,
      modelId: catalogModels[(index + 1) % catalogModels.length]!.id,
      questionText: questions[index % questions.length]!,
      demoKey: `smoke-analytics-question-${String(index + 1).padStart(3, '0')}`,
      askedAt: new Date(now - [0, 1, 2, 4, 6, 9, 15, 22, 29, 38][index % 10]! * 86_400_000 - (index % 6) * 3_600_000),
    }));
    for (const question of questionEvents) {
      await tx.insert(studentQuestions).values(question).onConflictDoUpdate({
        target: studentQuestions.demoKey,
        set: {
          userId: question.userId,
          modelId: question.modelId,
          questionText: question.questionText,
          askedAt: question.askedAt,
        },
      });
    }
  });
  console.log('Dashboard smoke listo: 1 docente, 1 aula, 8 estudiantes, 24 visitas y 16 preguntas.');
}

try {
  await seed();
  const [[studentCount], [visitCount], [questionCount]] = await Promise.all([
    db.select({ value: count() }).from(users).where(and(eq(users.role, 'student'), inArray(users.demoKey, students.map((s) => s.key)))),
    db.select({ value: count() }).from(modelVisits).where(inArray(modelVisits.demoKey, Array.from({ length: 24 }, (_, i) => `smoke-analytics-visit-${String(i + 1).padStart(3, '0')}`))),
    db.select({ value: count() }).from(studentQuestions).where(inArray(studentQuestions.demoKey, Array.from({ length: 16 }, (_, i) => `smoke-analytics-question-${String(i + 1).padStart(3, '0')}`))),
  ]);
  if (studentCount?.value !== 8 || visitCount?.value !== 24 || questionCount?.value !== 16) {
    throw new Error(`Scoped smoke verification failed: ${studentCount?.value} students, ${visitCount?.value} visits, ${questionCount?.value} questions.`);
  }
  console.log('Verificación de claves smoke completada.');
} finally {
  await pool.end();
}
