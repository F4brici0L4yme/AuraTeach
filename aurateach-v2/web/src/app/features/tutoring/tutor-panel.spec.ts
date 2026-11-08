import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TutorAnswer, TutorApi, TutorQuestion } from './tutor-api';
import { TutorPanel } from './tutor-panel';

const tutorAnswer: TutorAnswer = {
  answer: 'La maceta contiene el suelo que sostiene la planta.',
  speechText: 'El suelo sostiene la planta.',
  locator: { kind: 'none' },
  sceneAction: { kind: 'none' },
};

class MockLocalRecognition {
  lang = '';
  interimResults = false;
  continuous = true;
  onresult: ((event: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  onend: (() => void) | null = null;
  start = vi.fn();
  stop = vi.fn();
  abort = vi.fn();
}

describe('TutorPanel', () => {
  let fixture: ComponentFixture<TutorPanel>;
  let apiAsk: ReturnType<typeof vi.fn>;
  let answerSubject: Subject<TutorAnswer>;
  let originalSpeechRecognition: PropertyDescriptor | undefined;
  let originalWebkitSpeechRecognition: PropertyDescriptor | undefined;
  let originalSpeechSynthesis: PropertyDescriptor | undefined;
  let originalUtterance: PropertyDescriptor | undefined;

  beforeEach(() => {
    answerSubject = new Subject<TutorAnswer>();
    apiAsk = vi.fn((question: TutorQuestion) => { void question; return answerSubject.asObservable(); });
    TestBed.configureTestingModule({
      imports: [TutorPanel],
      providers: [{ provide: TutorApi, useValue: { ask: apiAsk } }],
    });
    fixture = TestBed.createComponent(TutorPanel);
    fixture.componentRef.setInput('modelId', 'school-pot');
    fixture.componentRef.setInput('topic', 'Biología y ambiente');
    fixture.componentRef.setInput('sceneImages', () => [
      { viewId: 'front', dataUrl: 'data:image/jpeg;base64,front' },
      { viewId: 'back', dataUrl: 'data:image/jpeg;base64,back' },
    ]);
    fixture.detectChanges();

    originalSpeechRecognition = Object.getOwnPropertyDescriptor(window, 'SpeechRecognition');
    originalWebkitSpeechRecognition = Object.getOwnPropertyDescriptor(window, 'webkitSpeechRecognition');
    originalSpeechSynthesis = Object.getOwnPropertyDescriptor(window, 'speechSynthesis');
    originalUtterance = Object.getOwnPropertyDescriptor(globalThis, 'SpeechSynthesisUtterance');
    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: undefined });
    Object.defineProperty(window, 'webkitSpeechRecognition', { configurable: true, value: undefined });
  });

  afterEach(() => {
    fixture.destroy();
    restoreProperty(window, 'SpeechRecognition', originalSpeechRecognition);
    restoreProperty(window, 'webkitSpeechRecognition', originalWebkitSpeechRecognition);
    restoreProperty(window, 'speechSynthesis', originalSpeechSynthesis);
    restoreProperty(globalThis, 'SpeechSynthesisUtterance', originalUtterance);
    vi.restoreAllMocks();
  });

  it('sends a typed question with its model context and displays the tutor response', async () => {
    fixture.componentRef.setInput('sceneNodes', [{ nodePath: '/Guitarra/Tapa[0]', name: 'Tapa', type: 'mesh' }]);
    fixture.componentRef.setInput('selectedNodePath', '/Guitarra/Tapa[0]');
    fixture.detectChanges();
    openChat();
    await enterQuestion('¿Qué función cumple el suelo de la maceta?');
    await submitQuestion();

    expect(apiAsk).toHaveBeenCalledTimes(1);
    expect(apiAsk).toHaveBeenCalledWith(expect.objectContaining({
      question: '¿Qué función cumple el suelo de la maceta?',
      modelId: 'school-pot',
      topic: 'Biología y ambiente',
      selectedNodePath: '/Guitarra/Tapa[0]',
    }));
    answerSubject.next(tutorAnswer);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('¿Qué función cumple el suelo de la maceta?');
    expect(fixture.nativeElement.textContent).toContain(tutorAnswer.answer);
  });

  it('falls back to typing when browser speech recognition is unavailable', async () => {
    fixture.nativeElement.querySelector('.tutor-bubble')!.click();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Este navegador no ofrece dictado por voz. Prueba con Chrome o escribe tu pregunta.');
    const questionInput = fixture.nativeElement.querySelector('[aria-label="Pregunta al tutor"]') as HTMLInputElement | null;
    expect(questionInput).not.toBeNull();
    expect(questionInput?.placeholder).toContain('Pregunta sobre lo que observas');
    expect(apiAsk).not.toHaveBeenCalled();

    await enterQuestion('¿Qué partes tiene este modelo?');
    await submitQuestion();
    expect(apiAsk).toHaveBeenCalledWith(expect.objectContaining({ question: '¿Qué partes tiene este modelo?' }));
    answerSubject.next(tutorAnswer);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain(tutorAnswer.answer);
  });

  it('uses Chrome webkitSpeechRecognition without requiring processLocally', () => {
    class ChromeRecognition extends MockLocalRecognition {
      static active: ChromeRecognition | undefined;
      constructor() { super(); ChromeRecognition.active = this; }
    }
    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: undefined });
    Object.defineProperty(window, 'webkitSpeechRecognition', { configurable: true, value: ChromeRecognition });

    fixture.nativeElement.querySelector('.tutor-bubble')!.click();
    fixture.detectChanges();

    expect(ChromeRecognition.active?.start).toHaveBeenCalledOnce();
    expect(ChromeRecognition.active?.lang).toBe('es-PE');
    expect(fixture.nativeElement.textContent).toContain('Escuchando en Chrome');
  });

  it('sends a final local transcript once and automatically reads the voice answer', async () => {
    const speak = vi.fn();
    const synthesis = { cancel: vi.fn(), getVoices: vi.fn(() => []), speak };
    class MockUtterance {
      lang = '';
      voice: SpeechSynthesisVoice | null = null;
      onend: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor(readonly text: string) {}
    }
    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: MockLocalRecognition });
    Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: synthesis });
    Object.defineProperty(globalThis, 'SpeechSynthesisUtterance', { configurable: true, value: MockUtterance });
    class CapturingRecognition extends MockLocalRecognition {
      static active: CapturingRecognition | undefined;
      static created = 0;
      constructor() {
        super();
        CapturingRecognition.created += 1;
        CapturingRecognition.active = this;
      }
    }
    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: CapturingRecognition });
    fixture.nativeElement.querySelector('.tutor-bubble')!.click();
    fixture.detectChanges();

    expect(CapturingRecognition.active).toBeDefined();
    expect(CapturingRecognition.active?.lang).toBe('es-PE');
    expect(CapturingRecognition.active?.start).toHaveBeenCalledOnce();
    const result = { isFinal: true, 0: { transcript: '¿Por qué las hojas son verdes?' } };
    CapturingRecognition.active?.onresult?.({ resultIndex: 0, results: [result] });
    CapturingRecognition.active?.onend?.();
    fixture.detectChanges();

    expect(apiAsk).toHaveBeenCalledTimes(1);
    expect(apiAsk).toHaveBeenCalledWith(expect.objectContaining({ question: '¿Por qué las hojas son verdes?' }));
    answerSubject.next(tutorAnswer);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain(tutorAnswer.answer);
    expect(speak).toHaveBeenCalledTimes(1);
    expect(speak.mock.calls[0]?.[0]).toMatchObject({ text: tutorAnswer.speechText, lang: 'es-PE' });
    (speak.mock.calls[0]?.[0] as MockUtterance).onend?.();
    expect(CapturingRecognition.created).toBe(2);
    expect(CapturingRecognition.active?.start).toHaveBeenCalledOnce();
  });

  it('attaches locally rendered model views with every tutor question', async () => {
    openChat();
    await enterQuestion('¿Qué observo?');
    await submitQuestion();
    expect(apiAsk.mock.calls[0]?.[0]).toHaveProperty('sceneImages', [
      { viewId: 'front', dataUrl: 'data:image/jpeg;base64,front' },
      { viewId: 'back', dataUrl: 'data:image/jpeg;base64,back' },
    ]);
    expect(fixture.nativeElement.textContent).toContain('El archivo GLB original permanece en este equipo.');
  });

  function openChat(): void {
    fixture.nativeElement.querySelector('.tutor-bubble')!.click();
    fixture.detectChanges();
  }

  async function enterQuestion(question: string): Promise<void> {
    const panel = fixture.componentInstance as unknown as { draft: string };
    panel.draft = question;
    fixture.detectChanges();
    await fixture.whenStable();
  }

  async function submitQuestion(): Promise<void> {
    const panel = fixture.componentInstance as unknown as { submitTyped: (event: Event) => void };
    panel.submitTyped(new Event('submit', { cancelable: true }));
    fixture.detectChanges();
    await fixture.whenStable();
  }
});

function restoreProperty(target: object, key: string, descriptor: PropertyDescriptor | undefined): void {
  if (descriptor) Object.defineProperty(target, key, descriptor);
  else Reflect.deleteProperty(target, key);
}
