import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', title: 'quant · visão geral', loadComponent: () => import('./pages/overview.page').then(m => m.OverviewPage) },
  { path: 'operar', title: 'quant · operar', loadComponent: () => import('./pages/operate.page').then(m => m.OperatePage) },
  { path: 'boleta', title: 'quant · boleta', loadComponent: () => import('./pages/ticket.page').then(m => m.TicketPage) },
  { path: 'trades', title: 'quant · trades', loadComponent: () => import('./pages/trades.page').then(m => m.TradesPage) },
  { path: 'carteira', title: 'quant · carteira', loadComponent: () => import('./pages/portfolio.page').then(m => m.PortfolioPage) },
  { path: 'saude', title: 'quant · saúde', loadComponent: () => import('./pages/health.page').then(m => m.HealthPage) },
  { path: 'gestao', title: 'quant · gestão', loadComponent: () => import('./pages/manage.page').then(m => m.ManagePage) },
  { path: '**', redirectTo: '' },
];
