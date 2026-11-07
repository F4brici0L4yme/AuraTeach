import type { NodePgDatabase } from 'drizzle-orm/node-postgres';
import type * as schema from '../../../../../infrastructure/database/schema.js';

export type AnalyticsDatabase = NodePgDatabase<typeof schema>;
