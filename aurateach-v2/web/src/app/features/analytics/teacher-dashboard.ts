import { Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButton } from '@angular/material/button';
import { DemoProfileSession } from '../identity/demo-profile-session';
import { TeacherAnalyticsApi, type AnalyticsFilters, type AnalyticsSummary, type QuestionsPage } from './teacher-analytics-api';

@Component({
  selector: 'app-teacher-dashboard',
  imports: [DatePipe, FormsModule, MatButton],
  template: `
    <main class="dashboard">
      <header class="topbar">
        <div><p class="eyebrow">AuraTeach · acompañamiento docente</p><h1>Panel de aula</h1><p class="sub">Observa la participación y decide qué explorar o reforzar.</p></div>
        <div class="toolbar">
          <label>Desde <input type="date" [(ngModel)]="from" name="from" /></label>
          <label>Hasta <input type="date" [(ngModel)]="to" name="to" /></label>
          <button matButton="outlined" (click)="refresh()">Aplicar</button>
          <button matButton="filled" (click)="exportCsv()" [disabled]="exporting()">{{ exporting() ? 'Preparando…' : 'Exportar CSV' }}</button>
          <button matButton (click)="leave()">Salir</button>
        </div>
      </header>
      @if (loading()) { <p class="status" role="status">Cargando datos del aula…</p> }
      @if (error()) { <p class="error" role="alert">{{ error() }} <button matButton (click)="refresh()">Reintentar</button></p> }
      @if (summary(); as data) {
        <section class="kpis" aria-label="Resumen del aula">
          <article class="kpi primary"><span>Alumnos activos</span><strong>{{ data.totals.activeStudents }}<small> / {{ data.totals.students }}</small></strong><p>con al menos una interacción en el periodo</p></article>
          <article class="kpi"><span>Visitas a modelos</span><strong>{{ data.totals.visits }}</strong><p>exploraciones registradas</p></article>
          <article class="kpi"><span>Preguntas investigadas</span><strong>{{ data.totals.questions }}</strong><p>preguntas finales enviadas al tutor</p></article>
          <article class="kpi attention"><span>Necesitan seguimiento</span><strong>{{ studentsNeedingSupport(data) }}</strong><p>poca o ninguna actividad reciente</p></article>
        </section>

        <section class="charts">
          <article class="panel trend-panel">
            <div class="panel-heading"><div><h2>Ritmo de exploración</h2><p>Visitas y preguntas por día</p></div><span class="period">{{ data.from }} — {{ data.to }}</span></div>
            <div class="legend"><span><i class="visit-dot"></i> Visitas</span><span><i class="question-dot"></i> Preguntas</span></div>
            <div class="trend-chart" role="img" aria-label="Gráfica de visitas y preguntas por día">
              @for (day of chartDays(data); track day.date) {
                <div class="day-column" [title]="day.date + ': ' + day.visits + ' visitas, ' + day.questions + ' preguntas'">
                  <div class="bars"><i class="visit-bar" [style.height.%]="barHeight(day.visits, maxDaily(data))"></i><i class="question-bar" [style.height.%]="barHeight(day.questions, maxDaily(data))"></i></div>
                  <small>{{ shortDate(day.date) }}</small>
                </div>
              }
              @if (!data.dailyActivity.length) { <p class="empty">No hay actividad en este periodo.</p> }
            </div>
          </article>
          <article class="panel model-panel">
            <div class="panel-heading"><div><h2>Modelos más explorados</h2><p>Qué despierta más curiosidad</p></div></div>
            @for (model of data.modelUsage.slice(0, 5); track model.modelId) {
              <div class="model-row"><span>{{ model.title }}</span><strong>{{ model.visitCount }} <small>visitas</small></strong><div class="model-track"><i [style.width.%]="barHeight(model.visitCount, maxModel(data))"></i></div></div>
            }
            @if (!data.modelUsage.length) { <p class="empty">Aún no hay modelos consultados.</p> }
          </article>
        </section>

        <section class="panel students-panel">
          <div class="panel-heading"><div><h2>Seguimiento de estudiantes</h2><p>La actividad baja ayuda a decidir a quién acompañar; no es una calificación.</p></div><span class="count">{{ data.students.length }} estudiantes</span></div>
          <div class="table-wrap"><table><thead><tr><th>Estudiante</th><th>Visitas</th><th>Preguntas</th><th>Última actividad</th><th>Seguimiento</th></tr></thead><tbody>
            @for (student of data.students; track student.studentId) {
              <tr><td><strong>{{ student.displayName }}</strong></td><td>{{ student.visitCount }}</td><td>{{ student.questionCount }}</td><td>{{ student.lastActivityAt ? (student.lastActivityAt | date:'d MMM, HH:mm') : 'Sin actividad' }}</td><td><span class="badge" [class.badge-attention]="needsSupport(student)">{{ needsSupport(student) ? 'Revisar y acompañar' : 'Participando' }}</span></td></tr>
            }
          </tbody></table></div>
        </section>

        <section class="panel questions-panel">
          <div class="panel-heading"><div><h2>Preguntas del aula</h2><p>Texto enviado al tutor para detectar temas de interés y dudas recurrentes.</p></div><span class="count">{{ questions()?.total ?? 0 }} registros</span></div>
          <div class="table-wrap"><table><thead><tr><th>Pregunta</th><th>Estudiante</th><th>Modelo</th><th>Fecha</th></tr></thead><tbody>
            @for (question of questions()?.items ?? []; track question.questionId) {
              <tr><td class="question-text">{{ question.questionText }}</td><td>{{ question.displayName }}</td><td>{{ question.modelTitle }}</td><td>{{ question.askedAt | date:'d MMM, HH:mm' }}</td></tr>
            }
          </tbody></table></div>
          <div class="pager"><button matButton (click)="loadQuestions(questionOffset() - 25)" [disabled]="questionOffset() === 0">Anterior</button><span>{{ questionRange() }}</span><button matButton (click)="loadQuestions(questionOffset() + 25)" [disabled]="questionOffset() + 25 >= (questions()?.total ?? 0)">Siguiente</button></div>
        </section>
        <footer>Datos sintéticos para demostración. El perfil docente actual solo controla la navegación de esta demo.</footer>
      }
    </main>
  `,
  styles: `
    :host { display:block; min-height:100vh; background:#fff; color:#172033; font-family:Arial,sans-serif; }
    .dashboard { max-width:1440px; margin:auto; padding:30px clamp(16px,3vw,42px) 48px; }
    .topbar { display:flex; justify-content:space-between; align-items:flex-end; gap:20px; margin-bottom:24px; } h1 { margin:4px 0; font-size:32px; } .sub,.panel-heading p { margin:5px 0 0; color:#66748a; } .eyebrow { color:#506bc0; font-size:12px; font-weight:bold; letter-spacing:.08em; text-transform:uppercase; margin:0; }
    .toolbar { display:flex; flex-wrap:wrap; align-items:end; gap:8px; } .toolbar label { display:grid; gap:5px; color:#59667c; font-size:12px; } input[type=date] { border:1px solid #d6ddea; border-radius:9px; padding:9px; background:white; color:#172033; font:inherit; }
    .kpis { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin-bottom:16px; } .kpi,.panel { background:white; border:1px solid #e5e9f1; border-radius:18px; box-shadow:0 4px 16px #23314e08; }
    .kpi { padding:18px 20px; } .kpi span { display:block; color:#66748a; font-size:13px; } .kpi strong { display:block; font-size:31px; margin:12px 0 4px; } .kpi strong small { font-size:16px; color:#8b96a8; } .kpi p { margin:0; color:#8792a4; font-size:12px; } .kpi.primary { border-top:3px solid #35445c; } .kpi.attention { border-top:3px solid #a58250; }
    .charts { display:grid; grid-template-columns:minmax(0,1.55fr) minmax(300px,.85fr); gap:16px; margin-bottom:16px; } .panel { padding:20px; margin-bottom:16px; min-width:0; }.panel-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; } h2 { margin:0; font-size:18px; } .panel-heading p { font-size:13px; }.period,.count { color:#738096; font-size:12px; white-space:nowrap; }
    .legend { display:flex; gap:16px; margin-top:17px; color:#758198; font-size:12px; }.legend i { display:inline-block; width:9px; height:9px; margin-right:5px; border-radius:50%; }.visit-dot { background:#55657d; }.question-dot { background:#9b8a71; }
    .trend-chart { height:190px; display:flex; align-items:stretch; gap:8px; overflow-x:auto; padding-top:18px; }.day-column { flex:1; min-width:22px; display:flex; flex-direction:column; justify-content:flex-end; align-items:center; gap:8px; }.bars { flex:1; width:100%; max-width:24px; display:flex; align-items:flex-end; justify-content:center; gap:3px; border-bottom:1px solid #edf0f5; }.bars i { display:block; width:8px; min-height:2px; border-radius:5px 5px 0 0; transition:height .35s ease; }.visit-bar { background:#607087; }.question-bar { background:#b3a38d; }.day-column small { color:#8792a4; font-size:9px; transform:rotate(-28deg); white-space:nowrap; }
    .model-row { display:grid; grid-template-columns:minmax(80px,1fr) auto; gap:7px 12px; margin-top:20px; font-size:13px; }.model-row>span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.model-row strong { font-size:12px; }.model-row strong small { color:#8792a4; font-weight:normal; }.model-track { grid-column:1/3; height:7px; background:#edf0f5; border-radius:8px; overflow:hidden; }.model-track i { display:block; height:100%; min-width:3px; border-radius:8px; background:#68778d; transition:width .4s ease; }
    .table-wrap { overflow:auto; margin-top:15px; } table { width:100%; border-collapse:collapse; font-size:13px; text-align:left; } th { color:#778399; font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:.04em; } td,th { padding:12px 10px; border-bottom:1px solid #edf0f5; } td { color:#445168; } td strong { color:#1e293e; }.badge { display:inline-block; border-radius:99px; padding:6px 9px; color:#26745f; background:#e6f7f1; font-size:11px; white-space:nowrap; }.badge-attention { color:#9a5e0c; background:#fff0d2; }.question-text { max-width:520px; min-width:240px; color:#25324a; }.pager { display:flex; align-items:center; justify-content:center; gap:18px; margin-top:10px; color:#778399; font-size:12px; }.empty,.status { padding:20px 0; color:#7b8798; text-align:center; }.error { color:#a32626; }.dashboard footer { text-align:center; color:#8a94a5; font-size:12px; margin-top:18px; }
    @media (max-width:920px) { .topbar { align-items:flex-start; flex-direction:column; } .kpis { grid-template-columns:repeat(2,minmax(0,1fr)); } .charts { grid-template-columns:1fr; } }
    @media (max-width:540px) { .kpis { grid-template-columns:1fr 1fr; gap:8px; }.kpi { padding:13px; }.kpi strong { font-size:24px; }.toolbar { align-items:stretch; }.toolbar label { flex:1; } .dashboard { padding-top:18px; } }
  `,
})
export class TeacherDashboard {
  private readonly api = inject(TeacherAnalyticsApi);
  private readonly session = inject(DemoProfileSession);
  protected readonly summary = signal<AnalyticsSummary | null>(null);
  protected readonly questions = signal<QuestionsPage | null>(null);
  protected readonly loading = signal(false);
  protected readonly exporting = signal(false);
  protected readonly error = signal('');
  protected readonly questionOffset = signal(0);
  protected from = this.offsetDate(29);
  protected to = this.offsetDate(0);

  constructor() { this.refresh(); }

  protected refresh(): void {
    const filters = this.filters();
    this.loading.set(true); this.error.set('');
    this.api.summary(filters).subscribe({
      next: (data) => { this.summary.set(data); this.loading.set(false); this.loadQuestions(0); },
      error: () => { this.loading.set(false); this.error.set('No se pudieron cargar los datos del aula.'); },
    });
  }

  protected loadQuestions(offset: number): void {
    const safeOffset = Math.max(0, offset);
    this.api.questions(this.filters(), safeOffset, 25).subscribe({
      next: (page) => { this.questions.set(page); this.questionOffset.set(safeOffset); },
      error: () => this.error.set('No se pudieron cargar las preguntas.'),
    });
  }

  protected exportCsv(): void {
    this.exporting.set(true);
    this.api.exportCsv(this.filters()).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob); const anchor = document.createElement('a');
        anchor.href = url; anchor.download = 'aurateach-reporte-aula.csv'; anchor.click();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
        this.exporting.set(false);
      },
      error: () => { this.exporting.set(false); this.error.set('No se pudo exportar el reporte.'); },
    });
  }

  protected leave(): void { this.session.leave(); window.location.assign('/'); }
  protected studentsNeedingSupport(data: AnalyticsSummary): number { return data.students.filter((student) => this.needsSupport(student)).length; }
  protected needsSupport(student: AnalyticsSummary['students'][number]): boolean { return student.visitCount < 2 && student.questionCount === 0; }
  protected maxDaily(data: AnalyticsSummary): number { return Math.max(1, ...data.dailyActivity.flatMap((day) => [day.visits, day.questions])); }
  protected chartDays(data: AnalyticsSummary): AnalyticsSummary['dailyActivity'] {
    if (!data.from || !data.to) return data.dailyActivity;
    const first = new Date(`${data.from}T00:00:00Z`);
    const last = new Date(`${data.to}T00:00:00Z`);
    const dayCount = Math.floor((last.getTime() - first.getTime()) / 86_400_000) + 1;
    if (!Number.isFinite(dayCount) || dayCount < 1 || dayCount > 180) return data.dailyActivity;
    const activity = new Map(data.dailyActivity.map((day) => [day.date, day]));
    return Array.from({ length: dayCount }, (_, index) => {
      const date = new Date(first.getTime() + index * 86_400_000).toISOString().slice(0, 10);
      return activity.get(date) ?? { date, visits: 0, questions: 0 };
    });
  }
  protected maxModel(data: AnalyticsSummary): number { return Math.max(1, ...data.modelUsage.map((model) => model.visitCount)); }
  protected barHeight(value: number, max: number): number { return value === 0 ? 1 : Math.max(5, value / max * 100); }
  protected shortDate(date: string): string { return date.slice(5); }
  protected questionRange(): string {
    const total = this.questions()?.total ?? 0; const start = total ? this.questionOffset() + 1 : 0;
    return `${start}–${Math.min(this.questionOffset() + (this.questions()?.items.length ?? 0), total)} de ${total}`;
  }

  private filters(): AnalyticsFilters { return { from: this.from, to: this.to }; }
  private offsetDate(days: number): string { const date = new Date(); date.setDate(date.getDate() - days); return date.toISOString().slice(0, 10); }
}
