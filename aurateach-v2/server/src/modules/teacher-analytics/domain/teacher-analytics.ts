export interface DateRange {
  from?: Date;
  toExclusive?: Date;
}

export interface StudentParticipation {
  studentId: number;
  displayName: string;
  visitCount: number;
  questionCount: number;
  lastActivityAt: string | null;
}

export interface DailyActivity {
  date: string;
  visits: number;
  questions: number;
}

export interface ModelUsage {
  modelId: number;
  title: string;
  visitCount: number;
  questionCount: number;
}

export interface TeacherAnalyticsSummary {
  from: string | null;
  to: string | null;
  totals: {
    students: number;
    activeStudents: number;
    visits: number;
    questions: number;
  };
  students: StudentParticipation[];
  dailyActivity: DailyActivity[];
  modelUsage: ModelUsage[];
}

export interface StudentQuestionRecord {
  questionId: number;
  studentId: number;
  displayName: string;
  modelId: number;
  modelTitle: string;
  questionText: string;
  askedAt: string;
}

export interface TeacherQuestionPage {
  items: StudentQuestionRecord[];
  offset: number;
  limit: number;
  total: number;
}

export interface AnalyticsQuery extends DateRange {
  fromLabel: string | null;
  toLabel: string | null;
}
