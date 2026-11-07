export interface TutorSceneNode {
  nodePath: string;
  name: string;
  type: string;
}

export interface TutorScenePart {
  partId: string;
  label: string;
}

export interface AskTutorCommand {
  question: string;
  modelId: string;
  topic: string;
  selectedNodePath?: string;
  sceneNodes?: TutorSceneNode[];
  sceneParts?: TutorScenePart[];
  screenshotDataUrl?: string;
}

export type TutorLocator =
  | { kind: 'none'; reason?: string }
  | { kind: 'semantic-node'; nodePath: string; label: string; confidence: number }
  | { kind: 'image-point'; viewId: string; uv: [number, number]; label: string; confidence: number };

export type TutorSceneAction =
  | { kind: 'none' }
  | { kind: 'explode-part'; partId: string }
  | { kind: 'assemble' };

export interface AskTutorResult {
  answer: string;
  locator: TutorLocator;
  sceneAction: TutorSceneAction;
  speechText: string;
}

export interface AskTutorPort {
  execute(command: AskTutorCommand): Promise<AskTutorResult>;
}
