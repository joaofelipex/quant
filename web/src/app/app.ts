import { DatePipe } from '@angular/common';
import { Component, effect, inject } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService } from './core/auth.service';
import { StatusStore } from './core/status.store';
import { LoginPage } from './pages/login.page';
import { ThemeService } from './core/theme.service';
import { ConfirmHost } from './shared/confirm';
import { Icon } from './shared/icon';
import { Toasts } from './shared/toast';

const TAG = { ok: '[OK]', warn: '[atenção]', bad: '[parado]', '': '' } as const;

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, DatePipe, Icon, Toasts, ConfirmHost, LoginPage],
  styleUrl: './app.css',
  templateUrl: './app.html',
})
export class App {
  protected readonly auth = inject(AuthService);
  protected readonly store = inject(StatusStore);
  protected readonly theme = inject(ThemeService);
  protected readonly links = [
    { to: '/', label: 'Visão geral', short: 'Geral', icon: 'grid', exact: true },
    { to: '/observar', label: 'Observatório', short: 'Observar', icon: 'pulse', exact: false },
    { to: '/operar', label: 'Operar', short: 'Operar', icon: 'sliders', exact: false },
    { to: '/boleta', label: 'Boleta', short: 'Boleta', icon: 'ticket', exact: false },
    { to: '/ia', label: 'IA', short: 'IA', icon: 'cpu', exact: false },
    { to: '/trades', label: 'Trades', short: 'Trades', icon: 'bars', exact: false },
    { to: '/carteira', label: 'Carteira', short: 'Carteira', icon: 'pie', exact: false },
    { to: '/saude', label: 'Saúde', short: 'Saúde', icon: 'check', exact: false },
    { to: '/gestao', label: 'Gestão', short: 'Gestão', icon: 'server', exact: false },
  ];

  constructor() {
    this.auth.check();
    const title = inject(Title);
    effect(() => title.setTitle(`${TAG[this.store.banner().tone]} quant · controle`.trim()));  // a aba mostra o estado
  }
}
