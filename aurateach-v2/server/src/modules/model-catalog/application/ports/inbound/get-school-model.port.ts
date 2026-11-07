import type { SchoolModel } from '../../../domain/school-model.js';

export interface GetSchoolModelPort {
  execute(id: string): Promise<SchoolModel | null>;
}
