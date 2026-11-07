import dotenv from 'dotenv';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Pool } from 'pg';

const here = path.dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: path.resolve(here, '../../../.env') });

const databaseUrl = process.env['DATABASE_URL'];
if (!databaseUrl) throw new Error('DATABASE_URL is required. Copy .env.example to .env first.');

const pool = new Pool({ connectionString: databaseUrl });

try {
  const baseline = await pool.query<{ users: string; classrooms: string; enrollments: string; visits: string; questions: string }>(`
    select
      (select count(*) from users where demo_key = 'demo-teacher' or demo_key like 'demo-student-%')::text as users,
      (select count(*) from classrooms where demo_key = 'demo-classroom')::text as classrooms,
      (select count(*) from enrollments e join classrooms c on c.id = e.classroom_id where c.demo_key = 'demo-classroom')::text as enrollments,
      (select count(*) from model_visits where demo_key like 'demo-visit-%')::text as visits,
      (select count(*) from student_questions where demo_key like 'demo-question-%')::text as questions
  `);
  const actual = Object.fromEntries(Object.entries(baseline.rows[0] ?? {}).map(([key, value]) => [key, Number(value)]));
  const expected = { users: 13, classrooms: 1, enrollments: 12, visits: 36, questions: 18 };
  for (const [key, expectedCount] of Object.entries(expected)) {
    const count = actual[key];
    if (count !== expectedCount) throw new Error(`${key}: se esperaban ${expectedCount} filas base y hay ${count}`);
    console.log(`${key} base: ${count}`);
  }
  const catalogModels = await pool.query<{ count: string }>(
    'select count(*)::text as count from models where catalog_key is not null and asset_key is not null and thumbnail_key is not null',
  );
  const modelCount = Number(catalogModels.rows[0]?.count ?? 0);
  if (modelCount !== 18) throw new Error(`models: se esperaban 18 modelos del catálogo y hay ${modelCount}`);
  console.log(`modelos del catálogo: ${modelCount}`);
  const missingCatalogMetadata = await pool.query<{ count: string }>(
    "select count(*)::text as count from models where catalog_key is not null and (source is null or license is null)",
  );
  if (Number(missingCatalogMetadata.rows[0]?.count ?? 0) !== 0) {
    throw new Error('Hay modelos del catálogo sin fuente o licencia.');
  }
  const inactive = await pool.query<{ count: string }>(
    "select count(*)::text as count from users u where u.role = 'student' and not exists (select 1 from model_visits v where v.user_id = u.id and v.visited_at >= now() - interval '14 days')",
  );
  if (Number(inactive.rows[0]?.count ?? 0) < 2) throw new Error('Se esperaban al menos 2 alumnos sin visitas recientes.');
  console.log(`Alumnos sin visitas en 14 días: ${inactive.rows[0]?.count}`);
} finally {
  await pool.end();
}
