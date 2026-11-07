import { Component, inject } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { MatButton } from '@angular/material/button';
import { DemoProfileSession } from './demo-profile-session';

@Component({
  selector: 'app-profile-destination',
  imports: [MatButton],
  template: `
    <main>
      <h1>{{ title }}</h1>
      <p>Perfil activo: {{ profileName }}</p>
      <p>Esta vista se completará en el siguiente módulo.</p>
      <button matButton (click)="leave()">Salir</button>
    </main>
  `,
})
export class ProfileDestination {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly session = inject(DemoProfileSession);

  protected readonly title = String(this.route.snapshot.data['title'] ?? 'AuraTeach');
  protected readonly profileName = this.session.current()?.displayName ?? 'Perfil de demo';

  protected leave(): void {
    this.session.leave();
    void this.router.navigateByUrl('/');
  }
}
