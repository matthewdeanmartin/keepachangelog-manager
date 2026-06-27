import { Routes } from '@angular/router';
import { BoardComponent } from './features/board.component';
import { TicketDetailComponent } from './features/ticket-detail.component';
import { ChangelogComponent } from './features/changelog.component';
import { PreviewComponent } from './features/preview.component';
import { WorkspaceComponent } from './features/workspace.component';
import { HelpComponent } from './features/help.component';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'board' },
  { path: 'board', component: BoardComponent },
  { path: 'ticket/:id', component: TicketDetailComponent },
  { path: 'changelog', component: ChangelogComponent },
  { path: 'preview', component: PreviewComponent },
  { path: 'workspace', component: WorkspaceComponent },
  { path: 'help', component: HelpComponent },
  { path: '**', redirectTo: 'board' },
];
