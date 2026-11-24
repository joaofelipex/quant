import { DatePipe } from '@angular/common';
import { Component, effect, inject } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { StatusStore } from './core/status.store';

const TAG = { ok: '[OK]', warn: '[atenção]', bad: '[parado]', '': '' } as const;

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, DatePipe],
  styleUrl: './app.css',
  templateUrl: './app.html',
})
export class App {
  protected readonly store = inject(StatusStore);
  protected readonly links = [
    { to: '/', label: 'Visão geral', exact: true },
    { to: '/operar', label: 'Operar', exact: false },
    { to: '/trades', label: 'Trades', exact: false },
    { to: '/carteira', label: 'Carteira', exact: false },
    { to: '/saude', label: 'Saúde', exact: false },
    { to: '/gestao', label: 'Gestão', exact: false },
  ];

  constructor() {
    const title = inject(Title);
    effect(() => title.setTitle(`${TAG[this.store.banner().tone]} quant · controle`.trim()));  // a aba mostra o estado
  }
}
