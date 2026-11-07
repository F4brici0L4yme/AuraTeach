export interface TutorQuestionStorePort {
  recordQuestion(modelId: string, questionText: string): Promise<void>;
}
