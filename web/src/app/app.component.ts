import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <header class="topbar">
      <a class="brand" routerLink="/board">KATL <span>· Keep A Task Log</span></a>
      <nav>
        <a routerLink="/board" routerLinkActive="active">Board</a>
        <a routerLink="/changelog" routerLinkActive="active">Changelog</a>
        <a routerLink="/preview" routerLinkActive="active">Release preview</a>
      </nav>
    </header>
    <main><router-outlet /></main>
    <footer>
      <span>Browser-only · fragments round-trip with the <code>keepachangelog-manager</code> CLI</span>
    </footer>
  `,
  styles: [
    `
      :host { display: flex; flex-direction: column; min-height: 100vh; }
      .topbar {
        display: flex; align-items: center; gap: 2rem;
        padding: 0.75rem 1.5rem; background: #1f2933; color: #fff;
      }
      .brand { font-weight: 700; color: #fff; text-decoration: none; font-size: 1.1rem; }
      .brand span { font-weight: 400; opacity: 0.6; font-size: 0.85rem; }
      nav { display: flex; gap: 1.25rem; }
      nav a { color: #cbd2d9; text-decoration: none; padding: 0.25rem 0; }
      nav a.active { color: #fff; border-bottom: 2px solid #4da8da; }
      main { flex: 1; padding: 1.5rem; max-width: 1200px; margin: 0 auto; width: 100%; box-sizing: border-box; }
      footer { padding: 0.75rem 1.5rem; background: #f5f7fa; color: #7b8794; font-size: 0.8rem; text-align: center; }
    `,
  ],
})
export class AppComponent {}
