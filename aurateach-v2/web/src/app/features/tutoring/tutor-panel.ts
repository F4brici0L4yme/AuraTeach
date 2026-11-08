import { Component, effect, input, output, signal, viewChild, ElementRef, inject, OnDestroy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButton } from '@angular/material/button';
import type { components } from '../../core/api/generated/api-types';
import { TutorApi, type TutorAnswer } from './tutor-api';

type SceneNode = NonNullable<components['schemas']['TutorQuestion']['sceneNodes']>[number];
type ScenePart = NonNullable<components['schemas']['TutorQuestion']['sceneParts']>[number];
type SceneImage = NonNullable<components['schemas']['TutorQuestion']['sceneImages']>[number];
interface RecognitionResult { isFinal: boolean; 0: { transcript: string } }
interface RecognitionEvent { resultIndex: number; results: ArrayLike<RecognitionResult> }
interface LocalSpeechRecognition extends EventTarget {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: RecognitionEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
interface SpeechWindow extends Window {
  SpeechRecognition?: new () => LocalSpeechRecognition;
  webkitSpeechRecognition?: new () => LocalSpeechRecognition;
}

@Component({
  selector: 'app-tutor-panel',
  imports: [FormsModule, MatButton],
  template: `
    <button class="tutor-bubble" type="button" aria-label="Preguntar al tutor por voz" (click)="toggleFromBubble()">
      @if (listening()) { <span class="pulse"></span> }
      <span aria-hidden="true">{{ listening() ? '■' : '🎙' }}</span>
    </button>
    @if (opened()) {
      <section class="tutor-panel" aria-label="Chat con el tutor" aria-live="polite">
        <header>
          <div><strong>Explora con el tutor</strong><small>{{ status() }}</small></div>
          <button type="button" class="close" aria-label="Cerrar chat" (click)="opened.set(false)">×</button>
        </header>
        <div #messagesBox class="messages" aria-live="polite">
          @for (message of messages(); track message.id) {
            <article [class.student]="message.role === 'student'" [class.tutor]="message.role === 'tutor'">
              <small>{{ message.role === 'student' ? 'Tú' : 'Tutor' }}</small>
              <p>{{ message.text }}</p>
              @if (message.role === 'tutor' && message.audio) {
                <div class="audio-actions">
                  <button mat-button type="button" (click)="speak(message.text)">Repetir</button>
                  <button mat-button type="button" (click)="stopSpeaking()">Detener voz</button>
                </div>
              }
            </article>
          }
          @if (interimText()) { <article class="student interim"><small>Te escucho…</small><p>{{ interimText() }}</p></article> }
          @if (pending()) { <p class="working" role="status">El tutor está pensando…</p> }
        </div>
        <p class="privacy-note">Al enviar tu pregunta, se compartirán con DeepSeek hasta 5 vistas renderizadas del modelo para analizar su forma. El archivo GLB original permanece en este equipo.</p>
        <form (submit)="submitTyped($event)">
          <input aria-label="Pregunta al tutor" placeholder="Pregunta sobre lo que observas…" [(ngModel)]="draft" name="question" maxlength="1200" />
          <button matButton="filled" type="submit" [disabled]="pending() || !draft.trim()">Enviar</button>
        </form>
        @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
      </section>
    }
  `,
  styles: `
    :host { position: fixed; z-index: 8; right: 24px; bottom: 22px; font-family: Arial, sans-serif; color: #172033; }
    .tutor-bubble { position: absolute; right: 0; bottom: 0; width: 62px; height: 62px; border: 1px solid #dce2ed; border-radius: 50%; background: #fff; color: #26334a; font-size: 22px; box-shadow: 0 5px 18px #17203320; cursor: pointer; transition: transform 160ms ease, box-shadow 160ms ease; }
    .tutor-bubble:hover { transform: translateY(-2px); box-shadow: 0 8px 22px #17203328; }
    .pulse { position: absolute; inset: -7px; border: 2px solid #5578dd; border-radius: 50%; animation: pulse 1.2s infinite; }
    @keyframes pulse { 50% { transform: scale(1.12); opacity: .4; } }
    .tutor-panel { position: absolute; right: 0; bottom: 78px; width: min(420px, calc(100vw - 32px)); height: min(590px, calc(100dvh - 130px)); min-height: 320px; display: flex; flex-direction: column; overflow: hidden; border: 1px solid #dce2ed; border-radius: 20px; background: #fff; box-shadow: 0 12px 42px #20283c2e; }
    header { display:flex; align-items:center; justify-content:space-between; padding: 16px 18px; border-bottom:1px solid #e7ebf2; }
    header div { display:grid; gap:5px; } header small { color:#68758a; font-size:12px; } .close { border:0; background:transparent; font-size:26px; cursor:pointer; color:#526078; }
    .messages { flex:1; overflow:auto; display:flex; flex-direction:column; gap:10px; padding:14px; }
    article { max-width:92%; padding:10px 13px; border-radius:14px; background:#f0f3f8; }
    article.student { align-self:flex-end; background:#e4edff; } article.tutor { align-self:flex-start; }
    article small { color:#66748a; font-size:11px; } article p { white-space:pre-wrap; margin:5px 0 0; line-height:1.45; }
    .interim { opacity:.72; } .working { color:#68758a; font-size:13px; }
    form { display:flex; gap:8px; padding:12px; border-top:1px solid #e7ebf2; }
    .privacy-note { margin:0; padding:8px 13px 0; color:#66748a; font-size:11px; line-height:1.4; }
    input { flex:1; min-width:0; padding:11px 12px; border:1px solid #cdd6e4; border-radius:11px; font:inherit; }
    .audio-actions { display:flex; gap:4px; margin-top:6px; } .error { padding:0 14px 10px; color:#a32626; font-size:13px; }
    @media (max-width:600px) { :host { right:12px; bottom:14px; } .tutor-panel { right:-2px; width:calc(100vw - 24px); height:min(65dvh,560px); } }
  `,
})
export class TutorPanel implements OnDestroy {
  readonly modelId = input.required<string>();
  readonly topic = input.required<string>();
  readonly sceneNodes = input<SceneNode[]>([]);
  readonly sceneParts = input<ScenePart[]>([]);
  readonly selectedNodePath = input<string | null>(null);
  readonly sceneImages = input<(() => SceneImage[]) | null>(null);
  readonly locator = output<NonNullable<TutorAnswer['locator']>>();
  readonly sceneAction = output<NonNullable<TutorAnswer['sceneAction']>>();

  private readonly tutorApi = inject(TutorApi);
  private readonly messageBox = viewChild<ElementRef<HTMLElement>>('messagesBox');
  readonly opened = signal(false);
  readonly listening = signal(false);
  readonly pending = signal(false);
  readonly status = signal('Puedes escribir o dictar con Chrome');
  readonly error = signal('');
  readonly interimText = signal('');
  readonly messages = signal<{ id: number; role: 'student' | 'tutor'; text: string; audio?: boolean }[]>([
    { id: 1, role: 'tutor', text: '¡Hola! Todo lo que nos rodea es un laboratorio. ¿Qué detalle del modelo quieres investigar?' },
  ]);
  protected draft = '';
  private nextMessageId = 2;
  private currentQuestionFromVoice = false;
  private voiceSessionActive = false;
  private speechGeneration = 0;
  private recognition: LocalSpeechRecognition | null = null;
  private finalTranscript = '';
  private speechUtterance: SpeechSynthesisUtterance | null = null;

  constructor() {
    effect(() => {
      const box = this.messageBox()?.nativeElement;
      if (box) queueMicrotask(() => { box.scrollTop = box.scrollHeight; });
    });
  }

  ngOnDestroy(): void {
    this.stopRecognition();
    this.stopSpeaking();
  }

  protected toggleFromBubble(): void {
    if (this.listening()) {
      this.stopRecognition();
      return;
    }
    this.opened.set(true);
    this.voiceSessionActive = true;
    this.startLocalRecognition();
  }

  protected submitTyped(event: Event): void {
    event.preventDefault();
    const text = this.draft.trim();
    if (!text || this.pending()) return;
    this.draft = '';
    this.submit(text, false);
  }

  private startLocalRecognition(): void {
    this.error.set('');
    const ctor = (window as SpeechWindow).SpeechRecognition ?? (window as SpeechWindow).webkitSpeechRecognition;
    if (!ctor) {
      this.status.set('Este navegador no ofrece dictado por voz. Prueba con Chrome o escribe tu pregunta.');
      return;
    }
    const recognition = new ctor();
    recognition.lang = 'es-PE';
    recognition.continuous = false;
    recognition.interimResults = true;
    this.recognition = recognition;
    this.finalTranscript = '';
    recognition.onresult = (event) => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i]!;
        if (result.isFinal) this.finalTranscript += result[0].transcript;
        else interim += result[0].transcript;
      }
      this.interimText.set(interim || this.finalTranscript);
    };
    recognition.onerror = (event) => {
      this.status.set(event.error === 'not-allowed' || event.error === 'service-not-allowed'
        ? 'Permite el micrófono para usar el dictado.'
        : event.error === 'no-speech'
          ? 'No detecté voz. Toca el micrófono para intentarlo otra vez.'
          : 'Chrome no pudo iniciar el dictado. Puedes intentarlo otra vez o escribir.');
      this.listening.set(false);
    };
    recognition.onend = () => {
      this.listening.set(false);
      const text = this.finalTranscript.trim();
      this.interimText.set('');
      this.recognition = null;
      if (text) this.submit(text, true);
      else this.status.set('No se detectó una pregunta; puedes intentar otra vez o escribirla.');
    };
    try {
      recognition.start();
      this.listening.set(true);
      this.status.set('Escuchando en Chrome…');
    } catch {
      this.status.set('Dictado local no disponible; escribe tu pregunta.');
      this.recognition = null;
    }
  }

  private submit(question: string, fromVoice: boolean): void {
    if (this.pending()) return;
    this.error.set('');
    this.currentQuestionFromVoice = fromVoice;
    this.messages.update((items) => [...items, { id: this.nextMessageId++, role: 'student', text: question }]);
    this.pending.set(true);
    this.status.set('Consultando al tutor…');
    const sceneImages = this.sceneImages()?.() ?? [];
    this.tutorApi.ask({
      question,
      modelId: this.modelId(),
      topic: this.topic(),
      ...(this.selectedNodePath() ? { selectedNodePath: this.selectedNodePath()! } : {}),
      sceneNodes: this.sceneNodes(),
      sceneParts: this.sceneParts(),
      ...(sceneImages.length ? { sceneImages } : {}),
    }).subscribe({
      next: (answer) => {
        this.error.set('');
        this.messages.update((items) => [...items, { id: this.nextMessageId++, role: 'tutor', text: answer.answer, audio: fromVoice }]);
        if (answer.locator.kind !== 'none') this.locator.emit(answer.locator);
        if (answer.sceneAction.kind !== 'none') this.sceneAction.emit(answer.sceneAction);
        this.pending.set(false);
        this.status.set('Listo para explorar otra pregunta');
        if (fromVoice) this.speak(answer.speechText);
      },
      error: () => {
        this.pending.set(false);
        this.status.set('No se pudo conectar con el tutor');
        this.error.set('No se pudo obtener una respuesta ahora. Tu pregunta permanece visible; inténtalo de nuevo o revisa la conexión.');
      },
    });
  }

  protected speak(text: string): void {
    if (!('speechSynthesis' in window)) {
      this.error.set('La voz no está disponible en este navegador; la respuesta sigue visible.');
      return;
    }
    this.stopSpeaking();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'es-PE';
    const voices = window.speechSynthesis.getVoices();
    utterance.voice = voices.find((voice) => voice.lang.toLowerCase() === 'es-pe')
      ?? voices.find((voice) => voice.lang.toLowerCase().startsWith('es'))
      ?? null;
    this.speechUtterance = utterance;
    const generation = ++this.speechGeneration;
    utterance.onend = () => {
      if (generation !== this.speechGeneration) return;
      this.speechUtterance = null;
      if (this.voiceSessionActive) this.startLocalRecognition();
    };
    utterance.onerror = () => {
      if (generation !== this.speechGeneration) return;
      this.speechUtterance = null;
      if (this.voiceSessionActive) this.startLocalRecognition();
    };
    window.speechSynthesis.speak(utterance);
  }

  protected stopSpeaking(): void {
    this.speechGeneration += 1;
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    this.speechUtterance = null;
  }

  private stopRecognition(): void {
    this.voiceSessionActive = false;
    this.recognition?.stop();
    this.recognition = null;
    this.listening.set(false);
  }
}
