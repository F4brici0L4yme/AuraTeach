import dotenv from 'dotenv';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { eq } from 'drizzle-orm';
import { drizzle } from 'drizzle-orm/node-postgres';
import { Pool } from 'pg';
import { classrooms, enrollments, modelVisits, models, studentQuestions, users } from '../../src/infrastructure/database/schema.js';
import { readCatalogManifest, type CatalogManifestEntry } from '../../src/infrastructure/model-catalog/catalog-manifest.js';

const here = path.dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: path.resolve(here, '../../../.env') });

const databaseUrl = process.env['DATABASE_URL'];
if (!databaseUrl) throw new Error('DATABASE_URL is required. Copy .env.example to .env first.');

const pool = new Pool({ connectionString: databaseUrl });
const db = drizzle(pool);

const studentDefinitions = Array.from({ length: 12 }, (_, index) => ({
  key: `demo-student-${String(index + 1).padStart(2, '0')}`,
  displayName: `Alumno ${String(index + 1).padStart(2, '0')}`,
}));

const modelDemoKeys: Record<string, string> = {
  maceta: 'demo-model-maceta',
  lapicero: 'demo-model-lapicero',
};

const questionTexts = [
  '¿Qué función cumplen las raíces en esta planta?',
  '¿Cómo ayuda el suelo a retener el agua?',
  '¿Qué materiales forman el cuerpo del lapicero?',
  '¿Por qué algunas hojas son más grandes que otras?',
  '¿Qué pasaría si la planta recibiera menos luz?',
  '¿Cómo se relaciona la erosión con la lluvia?',
  '¿Qué pieza permite que avance la mina?',
  '¿Qué diferencias observas entre estos materiales?',
  '¿Cómo podríamos comprobar qué suelo absorbe más agua?',
  '¿Qué parte de la maceta drena el exceso de agua?',
  '¿Por qué el suelo pierde nutrientes?',
  '¿Qué cambiaría si reemplazamos una pieza del modelo?',
  '¿Cómo afecta la sombra al crecimiento de la planta?',
  '¿Qué evidencia muestra que el agua movió el suelo?',
  '¿Para qué sirve la punta metálica del lapicero?',
  '¿Qué experimento compararías para probar esta idea?',
  '¿Cómo influye el tamaño de las partículas en el drenaje?',
  '¿Qué otra pregunta podríamos investigar con este modelo?',
];

async function seed(): Promise<void> {
  const assetsDirectory = path.resolve(here, '../../assets/model-catalog');
  const catalogModels = (await readCatalogManifest(assetsDirectory)).models;
  if (catalogModels.length !== 18) {
    throw new Error(`Expected 18 school models in the manifest; found ${catalogModels.length}.`);
  }
  await db.transaction(async (tx) => {
    const [teacher] = await tx
      .insert(users)
      .values({ role: 'teacher', displayName: 'Docente demo', demoKey: 'demo-teacher' })
      .onConflictDoUpdate({ target: users.demoKey, set: { role: 'teacher', displayName: 'Docente demo' } })
      .returning({ id: users.id });

    const students: Array<(typeof studentDefinitions)[number] & { id: number }> = [];
    for (const student of studentDefinitions) {
      const [row] = await tx
        .insert(users)
        .values({ role: 'student', displayName: student.displayName, demoKey: student.key })
        .onConflictDoUpdate({
          target: users.demoKey,
          set: { role: 'student', displayName: student.displayName },
        })
        .returning({ id: users.id });
      students.push({ ...student, id: row!.id });
    }

    const [classroom] = await tx
      .insert(classrooms)
      .values({ teacherId: teacher!.id, name: 'Aula de demostración', demoKey: 'demo-classroom' })
      .onConflictDoUpdate({
        target: classrooms.demoKey,
        set: { teacherId: teacher!.id, name: 'Aula de demostración' },
      })
      .returning({ id: classrooms.id });

    await tx
      .insert(enrollments)
      .values(students.map((student) => ({ classroomId: classroom!.id, studentId: student.id })))
      .onConflictDoNothing();

    const seededModels: Array<CatalogManifestEntry & { id: number }> = [];
    for (const model of catalogModels) {
      const demoKey = modelDemoKeys[model.id] ?? null;
      let existing: { id: number } | undefined;
      if (demoKey) {
        [existing] = await tx
          .select({ id: models.id })
          .from(models)
          .where(eq(models.demoKey, demoKey))
          .limit(1);
      }
      const values = {
        demoKey,
        catalogKey: model.catalogKey,
        title: model.title,
        topic: model.topic,
        assetKey: model.asset,
        thumbnailKey: model.thumbnail,
        source: model.source,
        license: model.license,
      };
      const [row] = existing
        ? await tx.update(models).set(values).where(eq(models.id, existing.id)).returning({ id: models.id })
        : await tx
            .insert(models)
            .values(values)
            .onConflictDoUpdate({
              target: models.catalogKey,
              set: {
                title: model.title,
                topic: model.topic,
                assetKey: model.asset,
                thumbnailKey: model.thumbnail,
                source: model.source,
                license: model.license,
              },
            })
            .returning({ id: models.id });
      seededModels.push({ ...model, id: row!.id });
    }

    await tx.insert(models)
      .values({ demoKey: 'demo-model-local-upload', title: 'Modelo propio', topic: 'Exploración 3D' })
      .onConflictDoUpdate({
        target: models.demoKey,
        set: { title: 'Modelo propio', topic: 'Exploración 3D' },
      });

    const date = (dayOffset: number, hour: number): Date => {
      const result = new Date('2026-11-06T12:00:00.000Z');
      result.setUTCDate(result.getUTCDate() - dayOffset);
      result.setUTCHours(hour, 0, 0, 0);
      return result;
    };

    const visitAssignments = [
      ...Array.from({ length: 7 }, (_, index) => ({ studentIndex: 0, modelIndex: index % 3, day: index })),
      ...Array.from({ length: 6 }, (_, index) => ({ studentIndex: 1, modelIndex: index % 3, day: index + 1 })),
      ...Array.from({ length: 7 }, (_, index) => ({ studentIndex: 2, modelIndex: index % 3, day: index + 2 })),
      ...[3, 4, 5, 6].flatMap((studentIndex) =>
        Array.from({ length: 3 }, (_, index) => ({ studentIndex, modelIndex: (studentIndex + index) % 3, day: index + 4 })),
      ),
      ...[7, 8].flatMap((studentIndex) =>
        Array.from({ length: 2 }, (_, index) => ({ studentIndex, modelIndex: (studentIndex + index) % 3, day: 18 + index })),
      ),
    ];

    await tx
      .insert(modelVisits)
      .values(
        visitAssignments.map((visit, index) => ({
          userId: students[visit.studentIndex]!.id,
          modelId: seededModels[visit.modelIndex]!.id,
          demoKey: `demo-visit-${String(index + 1).padStart(2, '0')}`,
          visitedAt: date(visit.day, 8 + (index % 9)),
        })),
      )
      .onConflictDoNothing();

    const questionAssignments = [
      ...Array.from({ length: 5 }, (_, index) => ({ studentIndex: 0, questionIndex: index, day: index })),
      ...Array.from({ length: 4 }, (_, index) => ({ studentIndex: 1, questionIndex: index + 5, day: index + 1 })),
      ...Array.from({ length: 4 }, (_, index) => ({ studentIndex: 2, questionIndex: index + 9, day: index + 2 })),
      ...[3, 4, 5, 6].map((studentIndex, index) => ({ studentIndex, questionIndex: index + 13, day: index + 5 })),
      { studentIndex: 7, questionIndex: 17, day: 21 },
    ];

    await tx
      .insert(studentQuestions)
      .values(
        questionAssignments.map((question, index) => ({
          userId: students[question.studentIndex]!.id,
          modelId: seededModels[question.studentIndex % seededModels.length]!.id,
          questionText: questionTexts[question.questionIndex]!,
          demoKey: `demo-question-${String(index + 1).padStart(2, '0')}`,
          askedAt: date(question.day, 9 + (index % 8)),
        })),
      )
      .onConflictDoNothing();
  });

  console.log('Seed listo: 1 docente, 1 aula, 12 alumnos, 18 modelos escolares, 36 visitas y 18 preguntas.');
}

try {
  await seed();
} finally {
  await pool.end();
}
