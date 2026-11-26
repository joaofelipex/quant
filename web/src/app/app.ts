import { DatePipe } from '@angular/common';
import { Component, computed, effect, inject, signal } from '@angular/core';
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
  protected readonly groups = [
    { title: 'Acompanhar', links: [
      { to: '/', label: 'Visão geral', short: 'Geral', icon: 'grid' },
      { to: '/aovivo', label: 'Ao vivo', short: 'Ao vivo', icon: 'radio' },
      { to: '/observar', label: 'Observatório', short: 'Observar', icon: 'pulse' },
      { to: '/trades', label: 'Trades', short: 'Trades', icon: 'list' },
    ] },
    { title: 'Agir', links: [
      { to: '/operar', label: 'Operar', short: 'Operar', icon: 'sliders' },
      { to: '/boleta', label: 'Boleta', short: 'Boleta', icon: 'ticket' },
      { to: '/ia', label: 'IA', short: 'IA', icon: 'cpu' },
    ] },
    { title: 'Analisar', links: [
      { to: '/pesquisa', label: 'Pesquisa', short: 'Pesquisa', icon: 'flask' },
      { to: '/carteira', label: 'Carteira', short: 'Carteira', icon: 'pie' },
    ] },
    { title: 'Sistema', links: [
      { to: '/saude', label: 'Saúde', short: 'Saúde', icon: 'check' },
      { to: '/gestao', label: 'Gestão', short: 'Gestão', icon: 'server' },
    ] },
  ];
  private readonly links = this.groups.flatMap(g => g.links);
  /** No celular: quatro atalhos fixos e o resto na folha "Mais". */
  protected readonly tabs = ['/', '/aovivo', '/observar', '/ia'].map(to => this.links.find(l => l.to === to)!);
  protected readonly rest = this.links.filter(l => !this.tabs.includes(l));
  protected readonly more = signal(false);
  protected readonly themeLabel = computed(() => 'tema ' + (this.theme.theme() === 'dark' ? 'claro' : 'escuro'));
  /** Em que dinheiro o runner opera, sempre a vista. */
  protected readonly mode = computed(() => {
    const m = this.store.data()?.config?.['QUANT_MODE'];
    if (!m) return null;
    return m === 'live' ? { text: 'CONTA REAL', tone: 'bad' } : { text: m === 'paper' ? 'simulado' : 'conta de teste', tone: 'warn' };
  });

  constructor() {
    this.auth.check();
    const title = inject(Title);
    effect(() => title.setTitle(`${TAG[this.store.banner().tone]} quant · controle`.trim()));  // a aba mostra o estado
  }
}
