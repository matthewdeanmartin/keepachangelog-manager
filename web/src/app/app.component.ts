import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { CommitBarComponent } from './features/commit-bar.component';
import { KATL_VERSION } from './core/version';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, CommitBarComponent],
  template: `
    <a class="skip" href="#main">Skip to content</a>
    <header class="topbar">
      <a class="brand" routerLink="/board">KATL <span>· Keep A Task Log</span></a>
      <nav aria-label="Primary">
        <a routerLink="/board" routerLinkActive="active">Board</a>
        <a routerLink="/changelog" routerLinkActive="active">Changelog</a>
        <a routerLink="/preview" routerLinkActive="active">Release preview</a>
        <a routerLink="/workspace" routerLinkActive="active">Workspace</a>
        <a routerLink="/help" routerLinkActive="active">Help</a>
      </nav>
    </header>
    <main id="main"><router-outlet /></main>
    <app-commit-bar />
    <footer>
      <span
        >Browser-only · fragments round-trip with the <code>keepachangelog-manager</code> CLI ·
        <a routerLink="/help">v{{ version }}</a></span
      >
    </footer>
  `,
  styles: [
    `
      :host {
        display: flex;
        flex-direction: column;
        min-height: 100vh;
      }
      .skip {
        position: absolute;
        left: -999px;
        top: 0;
        background: #fff;
        color: #1f2933;
        padding: 0.5rem 0.9rem;
        z-index: 100;
      }
      .skip:focus {
        left: 0.5rem;
        top: 0.5rem;
      }
      .topbar {
        display: flex;
        align-items: center;
        gap: 2rem;
        padding: 0.75rem 1.5rem;
        background: #1f2933;
        color: #fff;
      }
      .brand {
        font-weight: 700;
        color: #fff;
        text-decoration: none;
        font-size: 1.1rem;
      }
      .brand span {
        font-weight: 400;
        opacity: 0.6;
        font-size: 0.85rem;
      }
      nav {
        display: flex;
        gap: 1.25rem;
      }
      nav a {
        color: #cbd2d9;
        text-decoration: none;
        padding: 0.25rem 0;
      }
      nav a.active {
        color: #fff;
        border-bottom: 2px solid #4da8da;
      }
      main {
        flex: 1;
        padding: 1.5rem;
        max-width: 1200px;
        margin: 0 auto;
        width: 100%;
        box-sizing: border-box;
      }
      footer {
        padding: 0.75rem 1.5rem;
        background: #f5f7fa;
        color: #7b8794;
        font-size: 0.8rem;
        text-align: center;
      }
      footer a {
        color: #7b8794;
      }
    `,
  ],
})
export class AppComponent {
  version = KATL_VERSION;
}
