export interface RecordDemoModelVisitPort {
  execute(modelCatalogId: string): Promise<boolean>;
}
