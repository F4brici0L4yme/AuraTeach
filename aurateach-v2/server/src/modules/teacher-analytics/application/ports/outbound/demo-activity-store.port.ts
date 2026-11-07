export interface DemoActivityStorePort {
  recordModelVisit(modelCatalogId: string, demoKey: string, visitedAt: Date): Promise<boolean>;
}
