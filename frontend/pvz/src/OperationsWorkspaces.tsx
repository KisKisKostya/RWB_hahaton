import { useEffect, useMemo, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { api } from './api';
import './OperationsWorkspaces.css';

type Props = {
  selectedPvzId: number;
  pvzList: Array<{ id: number; city: string; address: string; is_hub?: boolean }>;
  onRefresh?: () => void;
};

type OrderRow = {
  id: number;
  product_id: number;
  qty: number;
  status: string;
  buyer_pvz_id: number;
  buyer_city: string;
  created_at: string;
};

type ReturnRow = {
  id: number; order_id: number; product_name: string; qty: number; reason: string;
  condition: string; decision: string; refund_amount: number; status: string; created_at: string;
};

type Incident = {
  id: number; incident_type: string; severity: string; status: string; message: string;
  pvz_id: number | null; transfer_id: number | null; order_id: number | null;
  stock_item_id: number | null; resolution_note: string | null; created_at: string;
};

type Transfer = {
  id: number; product_name: string; qty: number; status: string; from_label: string;
  to_label: string; route_name: string | null; distance_km: number | null;
};

type FinanceSummary = {
  orders_count: number; gross_sales: number; returns_refunded: number; net_sales: number;
  commission: number; storage_fees: number; logistics_cost: number; seller_payout: number;
  pvz_accruals: number; completed_transfers: number;
  accruals: Array<{ id: number; type: string; amount: number; order_id: number | null; created_at: string }>;
};

type SellerPayout = {
  seller_id: number; seller_name: string; commission_rate: number; gross_sales: number;
  refunds: number; commission: number; storage_fee: number; payout: number; orders_count: number;
};

const money = (value: number) => new Intl.NumberFormat('ru-RU', {
  style: 'currency', currency: 'RUB', maximumFractionDigits: 2,
}).format(value || 0);

const dateTime = (value: string) => new Date(value).toLocaleString('ru-RU', {
  day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
});

function Banner({ message, onClose }: { message: string; onClose: () => void }) {
  if (!message) return null;
  return <div className="ops-message" role="status"><span>{message}</span><button onClick={onClose}>×</button></div>;
}

function OpsPanel({ title, note, children }: { title: string; note: string; children: ReactNode }) {
  return <section className="ops-panel"><header><div><h2>{title}</h2><p>{note}</p></div></header>{children}</section>;
}

export function ReturnsWorkspace({ selectedPvzId, pvzList, onRefresh }: Props) {
  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [returns, setReturns] = useState<ReturnRow[]>([]);
  const [orderId, setOrderId] = useState('');
  const [reason, setReason] = useState('Покупатель отказался от товара');
  const [condition, setCondition] = useState<'intact' | 'damaged'>('intact');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  const load = async () => {
    try {
      const [allOrders, allReturns] = await Promise.all([api.getOrders(), api.getReturns()]);
      setOrders(allOrders);
      setReturns(allReturns);
      if (!orderId) {
        const firstIssued = allOrders.find((row: OrderRow) => row.status === 'ISSUED');
        if (firstIssued) setOrderId(String(firstIssued.id));
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Не удалось загрузить возвраты');
    }
  };
  useEffect(() => { load(); }, []);

  const availableOrders = orders.filter((row) => row.status === 'ISSUED');
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await api.createReturn(Number(orderId), { reason, condition });
      setMessage(
        'Возврат #' + result.id + ' зарегистрирован. ' +
        (result.status === 'WAITING_TRANSFER' ? 'Товар поставлен в очередь грузового рейса.' :
          result.status === 'WAITING_SELLER' ? 'Создан инцидент по повреждённому товару.' :
            result.status === 'NEEDS_REVIEW' ? 'Создан инцидент: требуется решение по размещению.' :
              'Товар возвращён в доступный остаток ПВЗ.')
      );
      await load();
      onRefresh?.();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Не удалось зарегистрировать возврат');
    } finally { setBusy(false); }
  };

  return <div className="ops-stack">
    <Banner message={message} onClose={() => setMessage('')} />
    <div className="ops-intro"><div><span>ОПЕРАТОР · ОБРАТНАЯ ЛОГИСТИКА</span><h1>Возвраты товаров</h1><p>Возврат привязан к конкретной партии заказа. Целый товар возвращается на ПВЗ или отправляется на хаб попутным рейсом; повреждённый попадает в очередь на отправку продавцу.</p></div></div>
    <div className="ops-two-col">
      <OpsPanel title="Зарегистрировать возврат" note="Доступны только заказы со статусом «Выдан»">
        <form className="ops-form" onSubmit={submit}>
          <label>Заказ<select value={orderId} onChange={(e) => setOrderId(e.target.value)} required>
            <option value="">Выберите выданный заказ</option>
            {availableOrders.map((row) => <option key={row.id} value={row.id}>#{row.id} · товар #{row.product_id} · {row.qty} шт. · ПВЗ #{row.buyer_pvz_id}</option>)}
          </select></label>
          <label>Состояние товара<select value={condition} onChange={(e) => setCondition(e.target.value as 'intact' | 'damaged')}>
            <option value="intact">Целый, пригоден к повторной продаже</option>
            <option value="damaged">Повреждён</option>
          </select></label>
          <label>Причина<textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} minLength={3} required /></label>
          <button className="workspace-button primary" disabled={busy || !orderId || !availableOrders.length}>{busy ? 'Регистрируем…' : 'Зарегистрировать возврат'}</button>
          {!availableOrders.length && <p className="ops-hint">Нет заказов со статусом «Выдан». Сначала проведите тестовую выдачу в основном сценарии.</p>}
        </form>
      </OpsPanel>
      <OpsPanel title="Правила обработки" note="Решение определяется состоянием и вместимостью">
        <div className="ops-rules">
          <div><b>01</b><strong>Целый товар</strong><p>Проверяется свободная ёмкость ПВЗ. При нехватке места выбирается подключённый хаб и создаётся задача на попутный рейс.</p></div>
          <div><b>02</b><strong>Повреждённый товар</strong><p>Партия исключается из продажи и создаётся инцидент для подтверждения отправки продавцу.</p></div>
          <div><b>03</b><strong>Финансовая корректировка</strong><p>Сумма возврата записывается отрицательной проводкой и учитывается в выплате продавцу и финансовой сводке.</p></div>
        </div>
      </OpsPanel>
    </div>
    <OpsPanel title="История возвратов" note={returns.length + ' зарегистрировано'}>
      <div className="ops-table-wrap"><table className="ops-table"><thead><tr><th>Возврат</th><th>Заказ / товар</th><th>Состояние</th><th>Решение</th><th>Корректировка</th><th>Статус</th><th>Дата</th></tr></thead><tbody>
        {returns.map((row) => <tr key={row.id}><td>#{row.id}</td><td>#{row.order_id} · {row.product_name} · {row.qty} шт.</td><td>{row.condition === 'damaged' ? 'Повреждён' : 'Целый'}</td><td>{row.decision === 'keep' ? 'Остался на ПВЗ' : row.decision === 'relocate' ? 'На хаб' : 'Продавцу'}</td><td>{money(-row.refund_amount)}</td><td><span className={'ops-status ' + (row.status === 'PROCESSED' ? 'success' : 'warning')}>{row.status}</span></td><td>{dateTime(row.created_at)}</td></tr>)}
        {!returns.length && <tr><td colSpan={7} className="ops-empty">Возвратов пока нет</td></tr>}
      </tbody></table></div>
    </OpsPanel>
    <p className="ops-hint">Текущий выбранный ПВЗ: #{selectedPvzId}. Доступно ПВЗ сети: {pvzList.filter((row) => !row.is_hub).length}.</p>
  </div>;
}

export function IncidentsWorkspace({ onRefresh }: Props) {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [transfers, setTransfers] = useState<Transfer[]>([]);
  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [transferId, setTransferId] = useState('');
  const [orderId, setOrderId] = useState('');
  const [failureMessage, setFailureMessage] = useState('Грузовой рейс отменён перевозчиком');
  const [busyId, setBusyId] = useState<number | null>(null);
  const [message, setMessage] = useState('');
  const [maintenanceResult, setMaintenanceResult] = useState<any>(null);

  const load = async () => {
    try {
      const [items, allTransfers, allOrders] = await Promise.all([api.getIncidents(), api.listTransfers(), api.getOrders()]);
      setIncidents(items);
      setTransfers(allTransfers);
      setOrders(allOrders);
      if (!transferId) {
        const firstReady = allTransfers.find((row: Transfer) => row.status === 'READY_ON_ROUTE');
        if (firstReady) setTransferId(String(firstReady.id));
      }
      if (!orderId) {
        const firstActive = allOrders.find((row: OrderRow) => ['CREATED', 'ROUTE_SELECTED', 'RESERVED', 'ASSEMBLED', 'IN_TRANSIT', 'READY'].includes(row.status));
        if (firstActive) setOrderId(String(firstActive.id));
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Не удалось загрузить инциденты');
    }
  };
  useEffect(() => { load(); }, []);

  const runMaintenance = async () => {
    setBusyId(-1);
    try {
      const result = await api.runStockMaintenance();
      setMaintenanceResult(result);
      setMessage(
        'Проверка завершена: истекло партий — ' + result.expired_items +
        '; ПВЗ с обновлённым TOP — ' + result.top_rechecked_count + '.'
      );
      await load();
      onRefresh?.();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Не удалось проверить сроки хранения');
    } finally { setBusyId(null); }
  };

  const reportFailure = async (event: FormEvent) => {
    event.preventDefault();
    setBusyId(Number(transferId));
    try {
      await api.reportTransferFailure(Number(transferId), failureMessage);
      setMessage('Сбой зафиксирован. Перемещение возвращено в очередь ожидания рейса.');
      await load();
      onRefresh?.();
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Не удалось зарегистрировать сбой'); }
    finally { setBusyId(null); }
  };
  const cancelOrder = async () => {
    if (!orderId) return;
    setBusyId(Number(orderId));
    try {
      const result = await api.cancelOrder(Number(orderId));
      setMessage('Заказ отменён. Освобождено партий: ' + result.released_stock_lots + '.');
      await load(); onRefresh?.();
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Не удалось отменить заказ'); }
    finally { setBusyId(null); }
  };
  const failOrder = async () => {
    if (!orderId) return;
    setBusyId(Number(orderId));
    try {
      await api.failOrder(Number(orderId), 'Сбой маршрута заказа, требуется ручная проверка');
      setMessage('Сбой заказа зарегистрирован, создан инцидент.');
      await load();
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Не удалось отметить сбой заказа'); }
    finally { setBusyId(null); }
  };
  const retry = async (id: number) => {
    setBusyId(id);
    try {
      await api.retryTransfer(id);
      setMessage('Для перемещения #' + id + ' повторно назначен действующий рейс.');
      await load(); onRefresh?.();
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Подходящий рейс пока не найден'); }
    finally { setBusyId(null); }
  };
  const resolve = async (incident: Incident) => {
    setBusyId(incident.id);
    try {
      await api.resolveIncident(incident.id, {
        resolution_note: 'Проверено оператором; действие выполнено по регламенту',
        mark_sent_to_seller: incident.incident_type === 'DAMAGED_RETURN' || incident.incident_type === 'STOCK_EXPIRED',
      });
      setMessage('Инцидент #' + incident.id + ' закрыт.');
      await load(); onRefresh?.();
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Не удалось закрыть инцидент'); }
    finally { setBusyId(null); }
  };

  const readyTransfers = transfers.filter((row) => row.status === 'READY_ON_ROUTE');
  const activeOrders = orders.filter((row) => ['CREATED', 'ROUTE_SELECTED', 'RESERVED', 'ASSEMBLED', 'IN_TRANSIT', 'READY'].includes(row.status));
  const openCount = incidents.filter((row) => row.status === 'OPEN').length;

  return <div className="ops-stack">
    <Banner message={message} onClose={() => setMessage('')} />
    <div className="ops-intro"><div><span>ОПЕРАТОР · КОНТРОЛЬ ИСКЛЮЧЕНИЙ</span><h1>Сбои и инциденты</h1><p>Рейс можно вернуть в очередь и назначить повторно после восстановления маршрута. Отмена заказа освобождает зарезервированный товар и ёмкость.</p></div><div className="ops-kpi"><strong>{openCount}</strong><span>открытых инцидентов</span></div></div>
    <OpsPanel title="Сроки хранения и TOP-перепроверка" note="Проверяет storage_deadline, переводит просроченные партии в EXPIRED и обновляет устаревшие TOP-флаги">
      <div className="ops-actions">
        <button className="workspace-button primary" disabled={busyId !== null} onClick={runMaintenance}>{busyId === -1 ? 'Проверяем…' : 'Проверить сроки и обновить TOP'}</button>
      </div>
      {maintenanceResult && <p className="ops-hint">Последняя проверка: истекло партий {maintenanceResult.expired_items}; TOP обновлён для ПВЗ: {maintenanceResult.top_rechecked_pvz_ids.join(', ') || 'нет'}. Период перепроверки — {maintenanceResult.top_recheck_interval_days} дней.</p>}
      <p className="ops-hint">После истечения TTL партия исключается из продажи. Оператор подтверждает передачу продавцу через карточку созданного инцидента.</p>
    </OpsPanel>
    <div className="ops-two-col">
      <OpsPanel title="Сбой грузового рейса" note="Только перемещения, уже назначенные на рейс">
        <form className="ops-form" onSubmit={reportFailure}>
          <label>Перемещение<select value={transferId} onChange={(e) => setTransferId(e.target.value)} required><option value="">Выберите перемещение</option>{readyTransfers.map((row) => <option key={row.id} value={row.id}>#{row.id} · {row.product_name} · {row.from_label} → {row.to_label}</option>)}</select></label>
          <label>Что произошло<input value={failureMessage} onChange={(e) => setFailureMessage(e.target.value)} minLength={3} required /></label>
          <button className="workspace-button primary" disabled={!transferId || !readyTransfers.length || busyId !== null}>Зарегистрировать сбой рейса</button>
          {!readyTransfers.length && <p className="ops-hint">Нет назначенных перемещений. Создайте тестовое перемещение в разделе «Перемещения».</p>}
        </form>
      </OpsPanel>
      <OpsPanel title="Отмена и сбой заказа" note="Тестирование сценариев исключения для клиентского заказа">
        <div className="ops-form">
          <label>Активный заказ<select value={orderId} onChange={(e) => setOrderId(e.target.value)}><option value="">Выберите заказ</option>{activeOrders.map((row) => <option key={row.id} value={row.id}>#{row.id} · {row.status} · товар #{row.product_id}</option>)}</select></label>
          <div className="ops-actions"><button className="workspace-button" disabled={!orderId || busyId !== null} onClick={cancelOrder}>Отменить заказ</button><button className="workspace-button danger" disabled={!orderId || busyId !== null} onClick={failOrder}>Зафиксировать сбой</button></div>
          <p className="ops-hint">Отмена возвращает зарезервированные партии в доступный остаток. Сбой переводит заказ в FAILED_ROUTE и создаёт запись для разбора.</p>
        </div>
      </OpsPanel>
    </div>
    <OpsPanel title="Журнал инцидентов" note={incidents.length + ' всего · ' + openCount + ' открыто'}>
      <div className="ops-incident-list">
        {incidents.map((incident) => <article key={incident.id} className="ops-incident">
          <div className="ops-incident-head"><div><span className={'ops-severity ' + incident.severity}>{incident.severity === 'high' ? 'Высокий приоритет' : 'Обычный приоритет'}</span><strong>#{incident.id} · {incident.incident_type}</strong></div><span className={'ops-status ' + (incident.status === 'RESOLVED' ? 'success' : 'warning')}>{incident.status === 'RESOLVED' ? 'Закрыт' : 'Открыт'}</span></div>
          <p>{incident.message}</p>
          <small>{dateTime(incident.created_at)}{incident.order_id ? ' · заказ #' + incident.order_id : ''}{incident.transfer_id ? ' · перемещение #' + incident.transfer_id : ''}</small>
          {incident.resolution_note && <small>Решение: {incident.resolution_note}</small>}
          {incident.status === 'OPEN' && <div className="ops-actions">
            {incident.transfer_id && <button className="workspace-button" disabled={busyId !== null} onClick={() => retry(incident.transfer_id!)}>Повторить назначение рейса</button>}
            <button className="workspace-button primary" disabled={busyId !== null} onClick={() => resolve(incident)}>Закрыть инцидент</button>
          </div>}
        </article>)}
        {!incidents.length && <div className="ops-empty">Инцидентов нет. Они появятся при сбое рейса, истечении TTL, повреждении возврата или нехватке места.</div>}
      </div>
    </OpsPanel>
  </div>;
}

export function FinanceWorkspace({ selectedPvzId, pvzList }: Props) {
  const [summary, setSummary] = useState<FinanceSummary | null>(null);
  const [payouts, setPayouts] = useState<SellerPayout[]>([]);
  const [selectedSeller, setSelectedSeller] = useState('all');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [finance, sellerRows] = await Promise.all([
        api.getFinanceSummary(selectedPvzId),
        api.getFinanceSellerPayouts(),
      ]);
      setSummary(finance);
      setPayouts(sellerRows);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Не удалось загрузить финансовую сводку');
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [selectedPvzId]);

  const shownPayouts = useMemo(
    () => selectedSeller === 'all' ? payouts : payouts.filter((row) => row.seller_id === Number(selectedSeller)),
    [payouts, selectedSeller],
  );
  const statCards = summary ? [
    ['Продажи до возвратов', summary.gross_sales],
    ['Возвраты', -summary.returns_refunded],
    ['Комиссия', summary.commission],
    ['Хранение', summary.storage_fees],
    ['Логистика', -summary.logistics_cost],
    ['Выплаты продавцам', summary.seller_payout],
    ['Начисления ПВЗ', summary.pvz_accruals],
  ] as Array<[string, number]> : [];

  return <div className="ops-stack">
    <Banner message={message} onClose={() => setMessage('')} />
    <div className="ops-intro"><div><span>ОПЕРАТОР · ФИНАНСОВАЯ МОДЕЛЬ</span><h1>Экономика Mesh</h1><p>Расчёты выполняются на backend по тарифам хранения, локальной/хабовой логистики и индивидуальной комиссии продавца.</p></div><button className="workspace-button" onClick={load} disabled={loading}>{loading ? 'Обновляем…' : 'Обновить расчёт'}</button></div>
    <div className="ops-finance-scope">Сводка по выбранному ПВЗ: <strong>#{selectedPvzId} · {pvzList.find((row) => row.id === selectedPvzId)?.address || 'ПВЗ'}</strong></div>
    <div className="ops-finance-grid">
      {statCards.map(([label, amount]) => <article key={label} className="ops-finance-card"><span>{label}</span><strong className={amount < 0 ? 'negative' : ''}>{money(amount)}</strong></article>)}
    </div>
    {summary && <div className="ops-two-col">
      <OpsPanel title="Сводные показатели" note="Фактические записи из базы и тарифные расчёты">
        <dl className="ops-finance-details">
          <div><dt>Количество завершённых заказов</dt><dd>{summary.orders_count}</dd></div>
          <div><dt>Чистые продажи</dt><dd>{money(summary.net_sales)}</dd></div>
          <div><dt>Завершённые грузовые перемещения</dt><dd>{summary.completed_transfers}</dd></div>
          <div><dt>Расчётная маржа после логистики и начислений ПВЗ</dt><dd>{money(summary.commission - summary.logistics_cost - summary.pvz_accruals)}</dd></div>
        </dl>
      </OpsPanel>
      <OpsPanel title="Из чего складывается стоимость" note="Базовые демонстрационные ставки проекта">
        <div className="ops-rules">
          <div><b>01</b><strong>Хранение</strong><p>5 ₽ за единицу в сутки, с округлением количества дней вверх.</p></div>
          <div><b>02</b><strong>Локальный маршрут</strong><p>80 ₽ + 6 ₽/км + сборка 20 ₽.</p></div>
          <div><b>03</b><strong>Маршрут через хаб</strong><p>120 ₽ + 3,5 ₽/км + обработка 40 ₽.</p></div>
        </div>
      </OpsPanel>
    </div>}
    <OpsPanel title="Расчёт выплат продавцам" note="Комиссия применяется по ставке конкретного продавца">
      <div className="ops-filter-row"><label>Продавец<select value={selectedSeller} onChange={(e) => setSelectedSeller(e.target.value)}><option value="all">Все продавцы</option>{payouts.map((row) => <option key={row.seller_id} value={row.seller_id}>{row.seller_name} · {(row.commission_rate * 100).toFixed(0)}%</option>)}</select></label></div>
      <div className="ops-table-wrap"><table className="ops-table"><thead><tr><th>Продавец</th><th>Заказы</th><th>Продажи</th><th>Возвраты</th><th>Комиссия</th><th>Хранение</th><th>К выплате</th></tr></thead><tbody>
        {shownPayouts.map((row) => <tr key={row.seller_id}><td>{row.seller_name} <small>({(row.commission_rate * 100).toFixed(0)}%)</small></td><td>{row.orders_count}</td><td>{money(row.gross_sales)}</td><td>{money(row.refunds)}</td><td>{money(row.commission)}</td><td>{money(row.storage_fee)}</td><td><strong>{money(row.payout)}</strong></td></tr>)}
        {!shownPayouts.length && <tr><td colSpan={7} className="ops-empty">Пока нет завершённых продаж.</td></tr>}
      </tbody></table></div>
    </OpsPanel>
    {summary && <OpsPanel title="Последние проводки" note="Положительные суммы — начисления; отрицательные — корректировки и возвраты">
      <div className="ops-table-wrap"><table className="ops-table"><thead><tr><th>Операция</th><th>Заказ</th><th>Дата</th><th>Сумма</th></tr></thead><tbody>
        {summary.accruals.map((row) => <tr key={row.id}><td>{row.type}</td><td>{row.order_id ? '#' + row.order_id : '—'}</td><td>{dateTime(row.created_at)}</td><td className={row.amount < 0 ? 'negative' : ''}>{money(row.amount)}</td></tr>)}
        {!summary.accruals.length && <tr><td colSpan={4} className="ops-empty">Проводок пока нет.</td></tr>}
      </tbody></table></div>
    </OpsPanel>}
    <p className="ops-hint">Финансовые тарифы — демонстрационные. Сводка рассчитана по данным локальной базы MVP и не является бухгалтерской отчётностью.</p>
  </div>;
}
