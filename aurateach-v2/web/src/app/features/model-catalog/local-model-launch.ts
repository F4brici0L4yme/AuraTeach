import { Injectable, signal } from '@angular/core';

/** Holds a selected local file only during the current in-app navigation. */
@Injectable({ providedIn: 'root' })
export class LocalModelLaunch {
  private readonly selectedFile = signal<File | null>(null);

  begin(file: File): void {
    this.selectedFile.set(file);
  }

  take(): File | null {
    const file = this.selectedFile();
    this.selectedFile.set(null);
    return file;
  }
}
