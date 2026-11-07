import { sql } from 'drizzle-orm';
import {
  bigint,
  check,
  foreignKey,
  index,
  pgTable,
  primaryKey,
  text,
  timestamp,
  unique,
} from 'drizzle-orm/pg-core';

export const users = pgTable(
  'users',
  {
    id: bigint('id', { mode: 'number' }).generatedAlwaysAsIdentity().primaryKey(),
    role: text('role').notNull(),
    displayName: text('display_name').notNull(),
    demoKey: text('demo_key'),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [
    unique('users_demo_key_unique').on(table.demoKey),
    check('users_role_check', sql`${table.role} in ('teacher', 'student')`),
  ],
);

export const classrooms = pgTable(
  'classrooms',
  {
    id: bigint('id', { mode: 'number' }).generatedAlwaysAsIdentity().primaryKey(),
    teacherId: bigint('teacher_id', { mode: 'number' }).notNull(),
    name: text('name').notNull(),
    demoKey: text('demo_key'),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [
    foreignKey({ columns: [table.teacherId], foreignColumns: [users.id], name: 'classrooms_teacher_id_fk' }),
    unique('classrooms_demo_key_unique').on(table.demoKey),
    index('classrooms_teacher_id_idx').on(table.teacherId),
  ],
);

export const enrollments = pgTable(
  'enrollments',
  {
    classroomId: bigint('classroom_id', { mode: 'number' }).notNull(),
    studentId: bigint('student_id', { mode: 'number' }).notNull(),
  },
  (table) => [
    primaryKey({ columns: [table.classroomId, table.studentId], name: 'enrollments_pk' }),
    foreignKey({ columns: [table.classroomId], foreignColumns: [classrooms.id], name: 'enrollments_classroom_id_fk' }),
    foreignKey({ columns: [table.studentId], foreignColumns: [users.id], name: 'enrollments_student_id_fk' }),
    index('enrollments_student_id_idx').on(table.studentId),
  ],
);

export const models = pgTable(
  'models',
  {
    id: bigint('id', { mode: 'number' }).generatedAlwaysAsIdentity().primaryKey(),
    title: text('title').notNull(),
    topic: text('topic').notNull(),
    demoKey: text('demo_key'),
    catalogKey: text('catalog_key'),
    assetKey: text('asset_key'),
    thumbnailKey: text('thumbnail_key'),
    source: text('source'),
    license: text('license'),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [
    unique('models_demo_key_unique').on(table.demoKey),
    unique('models_catalog_key_unique').on(table.catalogKey),
  ],
);

export const modelVisits = pgTable(
  'model_visits',
  {
    id: bigint('id', { mode: 'number' }).generatedAlwaysAsIdentity().primaryKey(),
    userId: bigint('user_id', { mode: 'number' }).notNull(),
    modelId: bigint('model_id', { mode: 'number' }).notNull(),
    demoKey: text('demo_key'),
    visitedAt: timestamp('visited_at', { withTimezone: true }).notNull(),
  },
  (table) => [
    foreignKey({ columns: [table.userId], foreignColumns: [users.id], name: 'model_visits_user_id_fk' }),
    foreignKey({ columns: [table.modelId], foreignColumns: [models.id], name: 'model_visits_model_id_fk' }),
    unique('model_visits_demo_key_unique').on(table.demoKey),
    index('model_visits_user_id_idx').on(table.userId),
    index('model_visits_model_id_idx').on(table.modelId),
    index('model_visits_visited_at_idx').on(table.visitedAt),
  ],
);

export const studentQuestions = pgTable(
  'student_questions',
  {
    id: bigint('id', { mode: 'number' }).generatedAlwaysAsIdentity().primaryKey(),
    userId: bigint('user_id', { mode: 'number' }).notNull(),
    modelId: bigint('model_id', { mode: 'number' }).notNull(),
    questionText: text('question_text').notNull(),
    demoKey: text('demo_key'),
    askedAt: timestamp('asked_at', { withTimezone: true }).notNull(),
  },
  (table) => [
    foreignKey({ columns: [table.userId], foreignColumns: [users.id], name: 'student_questions_user_id_fk' }),
    foreignKey({ columns: [table.modelId], foreignColumns: [models.id], name: 'student_questions_model_id_fk' }),
    unique('student_questions_demo_key_unique').on(table.demoKey),
    index('student_questions_user_id_idx').on(table.userId),
    index('student_questions_asked_at_idx').on(table.askedAt),
  ],
);
