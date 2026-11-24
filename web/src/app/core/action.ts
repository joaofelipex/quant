import { Observable } from 'rxjs';
import { errMsg } from './api.service';
import { ActionResult } from './models';
import { ToastService } from '../shared/toast';

/** Executa uma acao do painel e conta o resultado num toast; `done` roda em sucesso e em falha. */
export function runAction(toast: ToastService, call: Observable<ActionResult>, okText: (r: ActionResult) => string,
                          done?: () => void): void {
  call.subscribe({
    next: r => { toast.ok(okText(r)); done?.(); },
    error: e => { toast.error(`Falhou: ${errMsg(e)}`); done?.(); },
  });
}
