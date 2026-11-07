import { Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { MatButton } from '@angular/material/button';
import { MatIcon } from '@angular/material/icon';
import { DemoProfileSession } from './demo-profile-session';
import type { DemoRole } from './demo-profile-session';

const routeForRole: Record<DemoRole, string> = {
  teacher: '/docente/dashboard',
  student: '/alumno',
};

@Component({
  selector: 'app-profile-access',
  imports: [MatButton, MatIcon],
  template: `
    <main class="access-shell">
      <section class="welcome-card" aria-labelledby="welcome-title">
        <div class="brand-mark" aria-hidden="true"><mat-icon>auto_awesome</mat-icon></div>
        <p class="eyebrow">AURATEACH · LABORATORIO DE IDEAS</p>
        <h1 id="welcome-title">¡Hola! ¿Cuál es tu rol?</h1>
        <p class="intro">Explora, pregunta y descubre todo lo que hay detrás de lo cotidiano.</p>

        <section class="role-grid" aria-label="Seleccionar perfil">
          <button
            matButton
            class="role-card"
            type="button"
            data-testid="teacher-profile"
            [attr.aria-pressed]="selectedRole() === 'teacher'"
            (click)="selectRole('teacher')"
          >
            <span class="role-content">
              <span class="role-illustration teacher-illustration" aria-hidden="true"><mat-icon>school</mat-icon></span>
              <span class="role-name">Docente</span>
              <span class="role-description">Acompaña y guía la exploración</span>
            </span>
          </button>
          <button
            matButton
            class="role-card"
            type="button"
            data-testid="student-profile"
            [attr.aria-pressed]="selectedRole() === 'student'"
            (click)="selectRole('student')"
          >
            <span class="role-content">
              <span class="role-illustration student-illustration" aria-hidden="true"><mat-icon>person</mat-icon></span>
              <span class="role-name">Estudiante</span>
              <span class="role-description">Investiga y haz nuevas preguntas</span>
            </span>
          </button>
        </section>

      <p class="demo-note">Demo de aula · Elige un perfil para continuar</p>
      <button
        matButton
        class="enter-button"
        data-testid="enter"
        [disabled]="!selectedRole()"
        (click)="enter()"
      >
        Entrar <mat-icon aria-hidden="true">arrow_forward</mat-icon>
      </button>
      </section>
    </main>
  `,
  styles: `
    :host { display: block; min-height: 100dvh; color: #202b3c; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
    .access-shell { min-height: 100dvh; display: grid; place-items: center; padding: 28px; box-sizing: border-box; background: radial-gradient(ellipse at 50% 0%, #edf4ff 0, #f7f9fc 48%, #f2f5fa 100%); }
    .welcome-card { width: min(100%, 980px); box-sizing: border-box; padding: clamp(28px, 6vw, 64px); text-align: center; background: #fff; border: 1px solid #e1e8f2; border-radius: 28px; box-shadow: 0 24px 70px #273c5b12; }
    .brand-mark { width: 46px; height: 46px; display: grid; place-items: center; margin: 0 auto 14px; color: #315eb7; background: #edf3ff; border-radius: 15px; }
    .eyebrow { margin: 0 0 12px; color: #64748b; font-size: 11px; font-weight: 700; letter-spacing: .14em; }
    h1 { margin: 0; color: #1c2738; font-size: clamp(30px, 5vw, 44px); letter-spacing: -.04em; line-height: 1.15; }
    .intro { max-width: 540px; margin: 14px auto 36px; color: #68768b; font-size: 16px; line-height: 1.6; }
    .role-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; max-width: 650px; margin: 0 auto; }
    .role-card { min-height: 230px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 9px; padding: 22px; white-space: normal; color: #263247; background: #fff; border: 1px solid #dce4ef; border-radius: 20px; transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease, background 160ms ease; }
    .role-card:hover { transform: translateY(-3px); border-color: #9ab5eb; box-shadow: 0 12px 30px #345b9917; }
    .role-card[aria-pressed="true"] { border: 2px solid #527bd0; background: #f5f8ff; box-shadow: 0 0 0 4px #527bd01a; }
    .role-content { width: 100%; display: flex; flex-direction: column; align-items: center; gap: 9px; white-space: normal; }
    .role-illustration { width: 112px; height: 112px; display: grid; place-items: center; border-radius: 24px; }
    .role-illustration mat-icon { width: 52px; height: 52px; font-size: 52px; }
    .teacher-illustration { color: #3974ba; background: #eaf3ff; }
    .student-illustration { color: #7861bd; background: #f1edff; }
    .role-name { margin-top: 4px; color: #263247; font-size: 21px; font-weight: 700; }
    .role-description { color: #718096; font-size: 13px; line-height: 1.45; }
    .demo-note { margin: 27px 0 15px; color: #8692a4; font-size: 13px; }
    .enter-button { min-width: 220px; min-height: 48px; color: #fff; background: #315eb7; border-radius: 12px; font-weight: 650; }
    .enter-button mat-icon { margin-left: 8px; vertical-align: middle; }
    .enter-button:disabled { color: #8d99aa; background: #e8edf4; }
    @media (max-width: 560px) { .access-shell { padding: 14px; } .welcome-card { padding: 30px 18px; border-radius: 22px; } .intro { margin-bottom: 24px; font-size: 14px; } .role-grid { gap: 11px; } .role-card { min-height: 185px; padding: 14px 8px; } .role-illustration { width: 76px; height: 76px; border-radius: 20px; } .role-illustration mat-icon { font-size: 42px; width: 42px; height: 42px; } .role-name { font-size: 17px; } .role-description { font-size: 11px; } .enter-button { width: 100%; } }
    @media (prefers-reduced-motion: reduce) { .role-card { transition: none; } }
  `,
})
export class ProfileAccess {
  private readonly router = inject(Router);
  private readonly session = inject(DemoProfileSession);
  protected readonly selectedRole = signal<DemoRole | null>(null);

  protected selectRole(role: DemoRole): void {
    this.selectedRole.set(role);
  }

  protected enter(): void {
    const role = this.selectedRole();
    if (!role) return;

    this.session.enterAs(role);
    void this.router.navigateByUrl(routeForRole[role]);
  }
}
