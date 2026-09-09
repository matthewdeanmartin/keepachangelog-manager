import { inject } from '@angular/core';
import { Router, Routes } from '@angular/router';
import { SiteModeService } from './core/site-mode';
import { BoardComponent } from './features/board.component';
import { TicketDetailComponent } from './features/ticket-detail.component';
import { ChangelogComponent } from './features/changelog.component';
import { PreviewComponent } from './features/preview.component';
import { WorkspaceComponent } from './features/workspace.component';
import { HelpComponent } from './features/help.component';
import { ConflictsComponent } from './features/conflicts.component';

// Conflicts are a KATL-server concept; the lite (freemium) site has no
// server backend to conflict with.
const serverModeOnly = () =>
  inject(SiteModeService).isLite() ? inject(Router).parseUrl('/board') : true;

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'board' },
  { path: 'board', component: BoardComponent },
  { path: 'ticket/:id', component: TicketDetailComponent },
  { path: 'changelog', component: ChangelogComponent },
  { path: 'preview', component: PreviewComponent },
  { path: 'workspace', component: WorkspaceComponent },
  { path: 'conflicts', component: ConflictsComponent, canActivate: [serverModeOnly] },
  { path: 'help', component: HelpComponent },
  { path: '**', redirectTo: 'board' },
];
