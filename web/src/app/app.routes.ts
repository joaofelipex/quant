import { inject } from '@angular/core';
import { Router, Routes } from '@angular/router';
import { AuthService } from './core/auth.service';

/** So admin entra; os demais voltam para a visao geral (o servidor tambem barra com 403). */
const adminOnly = () => inject(AuthService).isAdmin() || inject(Router).createUrlTree(['/']);

export const routes: Routes = [
  { path: '', pathMatch: 'full', title: 'quant · visão geral', loadComponent: () => import('./pages/overview.page').then(m => m.OverviewPage) },
  { path: 'operar', title: 'quant · operar', loadComponent: () => import('./pages/operate.page').then(m => m.OperatePage) },
  { path: 'boleta', title: 'quant · boleta', loadComponent: () => import('./pages/ticket.page').then(m => m.TicketPage) },
  { path: 'conta', title: 'quant · minha conta', loadComponent: () => import('./pages/account.page').then(m => m.AccountPage) },
  { path: 'usuarios', title: 'quant · usuários', canActivate: [adminOnly], loadComponent: () => import('./pages/users.page').then(m => m.UsersPage) },
  { path: 'ia', title: 'quant · ia', loadComponent: () => import('./pages/agent.page').then(m => m.AgentPage) },
  { path: 'trades', title: 'quant · trades', loadComponent: () => import('./pages/trades.page').then(m => m.TradesPage) },
  { path: 'carteira', title: 'quant · carteira', loadComponent: () => import('./pages/portfolio.page').then(m => m.PortfolioPage) },
  { path: 'saude', title: 'quant · saúde', loadComponent: () => import('./pages/health.page').then(m => m.HealthPage) },
  { path: 'gestao', title: 'quant · gestão', loadComponent: () => import('./pages/manage.page').then(m => m.ManagePage) },
  { path: '**', redirectTo: '' },
];
