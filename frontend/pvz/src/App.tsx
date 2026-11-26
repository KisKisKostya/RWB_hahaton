import { useEffect, useMemo, useState } from 'react';
import type { CSSProperties, FormEvent, ReactNode } from 'react';
import { api } from './api';
import './App.css';

const CURRENT_PVZ_ID = 1;

type Tab = 'dash' | 'intake' | 'stock' | 'accruals';

type Capacity = {
  pvz_id: number;
  capacity_units: number;
  occupied: number;
  reserved: number;
  incoming: number;
  free: number;
  usable_limit: number;
  capacity_ok: boolean;
};

type StockItem = {
  id: number;
  product_id: number;
  pvz_id: number;
  qty: number;
  status: string;
  accepted_at: string;
  ttl_days: number;
  storage_deadline: string | null;
  top_flag: boolean;
  last_top_check: string | null;
};

type Accrual = {
  id: number;
  pvz_id: number;
  order_id: number | null;
  stock_item_id: number | null;
  type: string;
  amount: number;
  created_at: string;
};

type Product = {
  id: number;
  name: string;
  sku: string;
  category: string;
  price: number;
};

type Pvz = {
  id: number;
  city: string;
  address: string;
  capacity_units: number;
};

const money = (value: number) =>
  new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 0,
  }).format(value || 0);

const dateFormat = (value: string) =>
  new Date(value).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });

const dateTimeFormat = (value: string) =>
  new Date(value).toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });

const statusNames: Record<string, string> = {
  ACCEPTED: 'Принят',
  STORED: 'На хранении',
  RESERVED: 'Зарезервирован',
  ASSEMBLED: 'Собран',
  ISSUED: 'Выдан',
  RETURNED: 'Возвращён',
  RELOCATED: 'Перемещён',
  TO_HUB: 'В пути на хаб',
  TO_SELLER: 'Продавцу',
  EXPIRED: 'Срок истёк',
  DAMAGED: 'Повреждён',
};

const accrualNames: Record<string, string> = {
  intake: 'Приёмка товара',
  intake_fee: 'Приёмка товара',
  storage: 'Хранение',
  storage_fee: 'Хранение',
  assembly: 'Сборка заказа',
  issue_intake: 'Выдача заказа',
  pvz_income: 'Доход ПВЗ',
  relocation: 'Перемещение',
};

const iconNodes: Record<string, ReactNode> = {
  grid: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
  box: <><path d="m12 3 9 4.5v9L12 21l-9-4.5v-9L12 3Z" /><path d="m3.5 7.7 8.5 4.5 8.5-4.5M12 12.2V21M7.5 5.2l9 4.6" /></>,
  warehouse: <><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V10Z" /><path d="M9 21v-7h6v7M3 10h18" /></>,
  wallet: <><rect x="3" y="5" width="18" height="15" rx="2.5" /><path d="M3 9h18M16 15h.01M7 5V3h11" /></>,
  refresh: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M5.6 9A7 7 0 0 1 18 6.5L20 12M4 12l2 5.5A7 7 0 0 0 18.4 15" /></>,
  search: <><circle cx="10.8" cy="10.8" r="6.8" /><path d="m16 16 4.5 4.5" /></>,
  bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9ZM10 21h4" /></>,
  trend: <><path d="m3 16 6-6 4 4 8-9" /><path d="M15 5h6v6" /></>,
  alert: <><path d="M12 3 2.8 19a1.3 1.3 0 0 0 1.1 2h16.2a1.3 1.3 0 0 0 1.1-2L12 3Z" /><path d="M12 9v4M12 17h.01" /></>,
  plus: <><path d="M12 5v14M5 12h14" /></>,
  arrow: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  check: <><path d="m5 12 4 4L19 6" /></>,
  pin: <><path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></>,
  chevron: <><path d="m7 10 5 5 5-5" /></>,
  menu: <><path d="M4 6h16M4 12h16M4 18h16" /></>,
  close: <><path d="m6 6 12 12M18 6 6 18" /></>,
  spark: <><path d="m12 3 1.7 5.3L19 10l-5.3 1.7L12 17l-1.7-5.3L5 10l5.3-1.7L12 3ZM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8L19 16Z" /></>,
};

function Icon({ name, size = 20 }: { name: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {iconNodes[name] || iconNodes.grid}
    </svg>
  );
}

const navItems: { id: Tab; label: string; icon: string }[] = [
  { id: 'dash', label: 'Обзор', icon: 'grid' },
  { id: 'intake', label: 'Приёмка товара', icon: 'box' },
  { id: 'stock', label: 'Хранение', icon: 'warehouse' },
  { id: 'accruals', label: 'Начисления', icon: 'wallet' },
];

function App() {
  const [tab, setTab] = useState<Tab>('dash');
  const [capacity, setCapacity] = useState<Capacity | null>(null);
  const [stock, setStock] = useState<StockItem[]>([]);
  const [accruals, setAccruals] = useState<Accrual[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [pvz, setPvz] = useState<Pvz | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [stockFilter, setStockFilter] = useState('all');
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [cap, st, acc, prod, locations] = await Promise.all([
        api.getCapacity(CURRENT_PVZ_ID),
        api.getStock(CURRENT_PVZ_ID),
        api.getAccruals(CURRENT_PVZ_ID),
        api.getProducts(),
        api.getPvz(),
      ]);
      setCapacity(cap);
      setStock(st);
      setAccruals(acc);
      setProducts(prod);
      setPvz(locations.find((location: Pvz) => location.id === CURRENT_PVZ_ID) || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить данные');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const productById = useMemo(
    () => new Map(products.map((product) => [product.id, product])),
    [products],
  );

  const storedItems = stock.filter((item) => item.status === 'STORED' || item.status === 'ACCEPTED');
  const storedUnits = storedItems.reduce((sum, item) => sum + item.qty, 0);
  const expiringItems = storedItems.filter((item) => item.ttl_days <= 2);
  const totalAccrual = accruals.reduce((sum, item) => sum + Number(item.amount || 0), 0);
  const capacityPercent = capacity
    ? Math.min(100, Math.round((capacity.occupied / Math.max(capacity.capacity_units, 1)) * 100))
    : 0;

  const filteredStock = stock.filter((item) => {
    const product = productById.get(item.product_id);
    const text = (product?.name || 'Товар ' + item.product_id).toLowerCase();
    const matchesSearch =
      text.includes(search.toLowerCase()) ||
      String(item.id).includes(search) ||
      String(item.product_id).includes(search);
    const matchesFilter =
      stockFilter === 'all' ||
      (stockFilter === 'stored' && (item.status === 'STORED' || item.status === 'ACCEPTED')) ||
      (stockFilter === 'urgent' && item.ttl_days <= 2 && item.status === 'STORED') ||
      item.status === stockFilter;
    return matchesSearch && matchesFilter;
  });

  const currentTitle = navItems.find((item) => item.id === tab)?.label || 'Обзор';
  const now = new Date();
  const greeting = now.getHours() < 12 ? 'Доброе утро' : now.getHours() < 18 ? 'Добрый день' : 'Добрый вечер';

  const handleIntake = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setSubmitting(true);
    try {
      await api.intake(CURRENT_PVZ_ID, {
        product_id: Number(form.get('product_id')),
        qty: Number(form.get('qty')),
        top_flag: form.get('top_flag') === 'on',
      });
      formElement.reset();
      await loadData();
      setTab('stock');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка приёмки товара');
    } finally {
      setSubmitting(false);
    }
  };

  const handleRelocate = async (item: StockItem) => {
    try {
      await api.relocate(item.id, { target_pvz_id: 2, reason: 'manual' });
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка перемещения');
    }
  };

  const renderStockTable = (compact = false) => (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Товар</th>
            <th>Количество</th>
            <th>Статус</th>
            <th>До конца хранения</th>
            {!compact && <th>Особая отметка</th>}
            <th aria-label="Действия" />
          </tr>
        </thead>
        <tbody>
          {(compact ? stock.slice(0, 5) : filteredStock).map((item) => {
            const product = productById.get(item.product_id);
            const urgent = item.ttl_days <= 2 && item.status === 'STORED';
            return (
              <tr key={item.id}>
                <td>
                  <div className="product-cell">
                    <div className="product-thumb">{(product?.name || 'Т').slice(0, 1).toUpperCase()}</div>
                    <div>
                      <strong>{product?.name || 'Товар #' + item.product_id}</strong>
                      <span>SKU {product?.sku || '—'} · ID {item.id}</span>
                    </div>
                  </div>
                </td>
                <td><strong className="quantity">{item.qty} шт.</strong></td>
                <td>
                  <span className={'status-pill ' + (urgent ? 'status-warning' : item.status === 'STORED' ? 'status-success' : 'status-neutral')}>
                    <i />
                    {statusNames[item.status] || item.status}
                  </span>
                </td>
                <td>
                  <span className={urgent ? 'ttl-value ttl-urgent' : 'ttl-value'}>
                    <Icon name="clock" size={15} />
                    {item.ttl_days} дн.
                  </span>
                </td>
                {!compact && (
                  <td>
                    {item.top_flag ? <span className="top-label"><Icon name="spark" size={14} /> TOP-позиция</span> : <span className="muted">Обычная</span>}
                  </td>
                )}
                <td className="action-cell">
                  {item.status === 'STORED' && (
                    <button className="icon-button" title="Переместить на другой ПВЗ" onClick={() => handleRelocate(item)}>
                      <Icon name="arrow" size={17} />
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
          {(!compact && filteredStock.length === 0) && (
            <tr><td colSpan={6} className="empty-state">По вашему запросу ничего не найдено</td></tr>
          )}
          {(compact && stock.length === 0) && (
            <tr><td colSpan={6} className="empty-state">На этом ПВЗ пока нет товаров</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );

  const recentAccruals = [...accruals].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  const dailyAccruals = Array.from({ length: 7 }, (_, index) => {
    const date = new Date();
    date.setDate(date.getDate() - (6 - index));
    const key = date.toLocaleDateString('ru-RU');
    const amount = accruals
      .filter((item) => new Date(item.created_at).toLocaleDateString('ru-RU') === key)
      .reduce((sum, item) => sum + Number(item.amount || 0), 0);
    return { label: date.toLocaleDateString('ru-RU', { weekday: 'short' }).replace('.', ''), amount };
  });
  const maxDailyAccrual = Math.max(...dailyAccruals.map((item) => item.amount), 1);

  return (
    <div className="app-shell">
      <aside className={'sidebar ' + (mobileNavOpen ? 'sidebar-open' : '')}>
        <div className="brand">
          <div className="brand-mark"><span>W</span></div>
          <div className="brand-name">mesh<span>.</span><small>ПАНЕЛЬ ПВЗ</small></div>
          <button className="mobile-close" onClick={() => setMobileNavOpen(false)} aria-label="Закрыть меню"><Icon name="close" /></button>
        </div>

        <div className="workspace-label">РАБОЧЕЕ ПРОСТРАНСТВО</div>
        <div className="location-switch">
          <div className="location-icon"><Icon name="pin" size={18} /></div>
          <div className="location-copy">
            <strong>{pvz ? pvz.city : 'Пункт выдачи'}</strong>
            <span>{pvz?.address || 'Загрузка адреса…'}</span>
          </div>
          <Icon name="chevron" size={16} />
        </div>

        <div className="nav-caption">МЕНЮ</div>
        <nav className="sidebar-nav" aria-label="Основная навигация">
          {navItems.map((item) => (
            <button
              key={item.id}
              className={'nav-item ' + (tab === item.id ? 'active' : '')}
              onClick={() => { setTab(item.id); setMobileNavOpen(false); }}
            >
              <Icon name={item.icon} size={19} />
              <span>{item.label}</span>
              {item.id === 'stock' && expiringItems.length > 0 && <b className="nav-count">{expiringItems.length}</b>}
            </button>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="help-card">
            <div className="help-icon"><Icon name="spark" size={18} /></div>
            <strong>Нужна помощь?</strong>
            <p>Подсказки по работе с кабинетом и управлению остатками.</p>
            <button onClick={() => setError('Раздел помощи скоро появится')}>Центр поддержки <Icon name="arrow" size={14} /></button>
          </div>
          <div className="profile">
            <div className="avatar">К</div>
            <div className="profile-copy"><strong>Менеджер ПВЗ</strong><span>Администратор</span></div>
            <button className="profile-more" aria-label="Профиль"><span /><span /><span /></button>
          </div>
        </div>
      </aside>

      {mobileNavOpen && <button className="mobile-scrim" onClick={() => setMobileNavOpen(false)} aria-label="Закрыть меню" />}

      <main className="main-area">
        <header className="topbar">
          <div className="topbar-left">
            <button className="mobile-menu" onClick={() => setMobileNavOpen(true)} aria-label="Открыть меню"><Icon name="menu" /></button>
            <div className="breadcrumbs"><span>Кабинет ПВЗ</span><b>/</b><strong>{currentTitle}</strong></div>
          </div>
          <div className="topbar-right">
            <div className="today-date">{now.toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' })}</div>
            <button className="icon-button notification-button" aria-label="Уведомления" onClick={() => setTab('stock')}>
              <Icon name="bell" size={19} />
              {expiringItems.length > 0 && <i />}
            </button>
            <div className="topbar-avatar">К</div>
          </div>
        </header>

        <div className="page-content">
          <section className="page-heading">
            <div>
              <div className="eyebrow">{greeting}, команда</div>
              <h1>{tab === 'dash' ? 'Обзор пункта выдачи' : currentTitle}</h1>
              <p>{tab === 'dash'
                ? 'Всё важное о работе вашего пункта выдачи — в одном месте.'
                : tab === 'intake'
                  ? 'Добавляйте товары на хранение и отмечайте приоритетные позиции.'
                  : tab === 'stock'
                    ? 'Следите за остатками, статусами и сроками хранения товаров.'
                    : 'Контролируйте доходы пункта выдачи и историю начислений.'}</p>
            </div>
            <div className="heading-actions">
              <button className="button button-secondary" onClick={loadData} disabled={loading}>
                <Icon name="refresh" size={17} />
                Обновить
              </button>
              {tab !== 'intake' && (
                <button className="button button-primary" onClick={() => setTab('intake')}>
                  <Icon name="plus" size={18} />
                  Новая приёмка
                </button>
              )}
            </div>
          </section>

          {error && (
            <div className="alert-banner">
              <Icon name="alert" size={18} />
              <span>{error}</span>
              <button onClick={() => setError(null)} aria-label="Скрыть сообщение"><Icon name="close" size={17} /></button>
            </div>
          )}

          {loading && (
            <div className="loading-line"><span /> Обновляем данные ПВЗ…</div>
          )}

          {tab === 'dash' && (
            <>
              <section className="stats-grid">
                <article className="stat-card">
                  <div className="stat-top"><span>Загрузка ПВЗ</span><div className="stat-icon violet"><Icon name="warehouse" /></div></div>
                  <div className="stat-value">{capacity ? capacity.occupied : '—'}<small> / {capacity?.capacity_units ?? '—'} шт.</small></div>
                  <div className="stat-foot"><span className="stat-dot violet-dot" /> {capacityPercent}% от общей ёмкости</div>
                  <div className="mini-progress"><span style={{ width: capacityPercent + '%' }} /></div>
                </article>
                <article className="stat-card">
                  <div className="stat-top"><span>Товаров на хранении</span><div className="stat-icon blue"><Icon name="box" /></div></div>
                  <div className="stat-value">{storedUnits}<small> шт.</small></div>
                  <div className="stat-foot"><span className="stat-dot blue-dot" /> {storedItems.length} товарных позиций</div>
                  <div className="stat-note">Включая принятые и размещённые товары</div>
                </article>
                <article className="stat-card">
                  <div className="stat-top"><span>Начислено всего</span><div className="stat-icon green"><Icon name="wallet" /></div></div>
                  <div className="stat-value">{money(totalAccrual)}</div>
                  <div className="stat-foot"><span className="stat-dot green-dot" /> {accruals.length} операций в истории</div>
                  <div className="stat-note">Сумма по всем начислениям ПВЗ</div>
                </article>
                <article className="stat-card">
                  <div className="stat-top"><span>Требуют внимания</span><div className="stat-icon orange"><Icon name="alert" /></div></div>
                  <div className="stat-value">{expiringItems.length}<small> поз.</small></div>
                  <div className="stat-foot"><span className="stat-dot orange-dot" /> Осталось 2 дня или меньше</div>
                  <button className="stat-link" onClick={() => { setStockFilter('urgent'); setTab('stock'); }}>Проверить товары <Icon name="arrow" size={14} /></button>
                </article>
              </section>

              <section className="dashboard-grid">
                <article className="panel capacity-panel">
                  <div className="panel-heading">
                    <div><h2>Ёмкость пункта</h2><p>Текущая загрузка и свободное место</p></div>
                    <span className={'status-pill ' + (capacity?.capacity_ok ? 'status-success' : 'status-warning')}><i />{capacity?.capacity_ok ? 'В норме' : 'Лимит достигнут'}</span>
                  </div>
                  <div className="capacity-content">
                    <div className="capacity-ring" style={{ '--progress': capacityPercent + '%' } as CSSProperties}>
                      <div><strong>{capacityPercent}<small>%</small></strong><span>занято</span></div>
                    </div>
                    <div className="capacity-legend">
                      <div><span className="legend-dot used" /><span>Занято</span><strong>{capacity?.occupied ?? 0} шт.</strong></div>
                      <div><span className="legend-dot reserved" /><span>Зарезервировано</span><strong>{capacity?.reserved ?? 0} шт.</strong></div>
                      <div><span className="legend-dot free" /><span>Свободно</span><strong>{capacity?.free ?? 0} шт.</strong></div>
                      <div className="capacity-divider" />
                      <div className="capacity-total"><span>Доступная ёмкость</span><strong>{capacity?.usable_limit ?? 0} шт.</strong></div>
                    </div>
                  </div>
                  <div className="capacity-message"><Icon name="check" size={16} /> Резерв ёмкости учитывается автоматически при расчёте доступного места.</div>
                </article>

                <article className="panel income-panel">
                  <div className="panel-heading">
                    <div><h2>Динамика начислений</h2><p>Сумма операций за последние 7 дней</p></div>
                    <span className="chart-period">7 дней</span>
                  </div>
                  <div className="chart-total">{money(dailyAccruals.reduce((sum, item) => sum + item.amount, 0))}<span>за период</span></div>
                  <div className="bar-chart">
                    {dailyAccruals.map((item, index) => (
                      <div className="bar-column" key={index}>
                        <div className="bar-track"><span style={{ height: Math.max(5, (item.amount / maxDailyAccrual) * 100) + '%' }} title={money(item.amount)} /></div>
                        <small>{item.label}</small>
                      </div>
                    ))}
                  </div>
                </article>
              </section>

              <section className="panel recent-panel">
                <div className="panel-heading">
                  <div><h2>Остатки на ПВЗ</h2><p>Последние добавленные товарные позиции</p></div>
                  <button className="text-button" onClick={() => setTab('stock')}>Все товары <Icon name="arrow" size={15} /></button>
                </div>
                {renderStockTable(true)}
              </section>

              <section className="panel activity-panel">
                <div className="panel-heading">
                  <div><h2>Последние начисления</h2><p>Финансовые операции по вашему пункту</p></div>
                  <button className="text-button" onClick={() => setTab('accruals')}>Все начисления <Icon name="arrow" size={15} /></button>
                </div>
                <div className="activity-list">
                  {recentAccruals.slice(0, 4).map((item) => (
                    <div className="activity-row" key={item.id}>
                      <div className="activity-icon"><Icon name="wallet" size={17} /></div>
                      <div className="activity-copy"><strong>{accrualNames[item.type] || item.type}</strong><span>{dateTimeFormat(item.created_at)} · Операция #{item.id}</span></div>
                      <strong className="activity-amount">+{money(item.amount)}</strong>
                    </div>
                  ))}
                  {recentAccruals.length === 0 && <div className="empty-state">Начислений пока нет</div>}
                </div>
              </section>
            </>
          )}

          {tab === 'intake' && (
            <section className="intake-layout">
              <article className="panel intake-form-panel">
                <div className="panel-heading">
                  <div><h2>Новая приёмка</h2><p>Заполните информацию о поступившем товаре</p></div>
                  <div className="form-step">01 <span>/ 01</span></div>
                </div>
                <form className="intake-form" onSubmit={handleIntake}>
                  <label className="field-label" htmlFor="product_id">Товар <span>*</span></label>
                  <div className="select-wrap">
                    <select id="product_id" name="product_id" required defaultValue="">
                      <option value="" disabled>Выберите товар из каталога</option>
                      {products.map((product) => (
                        <option key={product.id} value={product.id}>{product.name} · {product.sku}</option>
                      ))}
                    </select>
                    <Icon name="chevron" size={17} />
                  </div>
                  <div className="field-hint">Выберите позицию из каталога товаров продавцов.</div>

                  <label className="field-label" htmlFor="qty">Количество <span>*</span></label>
                  <div className="input-wrap">
                    <input id="qty" name="qty" type="number" min="1" max="1000" placeholder="Например, 12" required />
                    <span>шт.</span>
                  </div>
                  <div className="field-hint">Количество единиц товара в текущей поставке.</div>

                  <div className="priority-option">
                    <div className="priority-icon"><Icon name="spark" size={18} /></div>
                    <div className="priority-copy"><strong>TOP-позиция</strong><span>Отметьте товар с высоким спросом для приоритетной локальной маршрутизации.</span></div>
                    <label className="switch"><input type="checkbox" name="top_flag" /><span /></label>
                  </div>

                  <div className="form-summary">
                    <div><span>Свободно сейчас</span><strong>{capacity?.free ?? '—'} шт.</strong></div>
                    <div><span>Резерв ёмкости</span><strong>{capacity ? Math.round(capacity.capacity_units - capacity.usable_limit) : '—'} шт.</strong></div>
                  </div>

                  <div className="form-actions">
                    <button type="button" className="button button-secondary" onClick={() => setTab('dash')}>Отмена</button>
                    <button type="submit" className="button button-primary" disabled={submitting || products.length === 0}>
                      {submitting ? 'Сохраняем…' : <><Icon name="plus" size={18} /> Принять товар</>}
                    </button>
                  </div>
                </form>
              </article>

              <aside className="intake-aside">
                <article className="panel side-info-card">
                  <div className="side-info-icon"><Icon name="check" size={20} /></div>
                  <h3>Перед приёмкой</h3>
                  <p>Система автоматически проверит, достаточно ли свободного места на пункте выдачи.</p>
                  <ul>
                    <li><Icon name="check" size={15} /> Проверка доступной ёмкости</li>
                    <li><Icon name="check" size={15} /> Расчёт срока хранения</li>
                    <li><Icon name="check" size={15} /> Автоматическое начисление за приёмку</li>
                  </ul>
                </article>
                <article className="tip-card">
                  <div><Icon name="spark" size={19} /><strong>Совет</strong></div>
                  <p>Помечайте товары с высоким спросом как TOP-позиции. Это помогает системе выбирать более быстрые локальные маршруты.</p>
                </article>
              </aside>
            </section>
          )}

          {tab === 'stock' && (
            <section className="panel stock-panel">
              <div className="panel-heading stock-heading">
                <div><h2>Товары на хранении</h2><p>Всего {stock.length} позиций · {storedUnits} единиц товара</p></div>
                <button className="button button-primary" onClick={() => setTab('intake')}><Icon name="plus" size={17} /> Новая приёмка</button>
              </div>
              <div className="table-toolbar">
                <div className="search-field"><Icon name="search" size={18} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Поиск по названию или ID" /></div>
                <div className="filter-tabs">
                  <button className={stockFilter === 'all' ? 'selected' : ''} onClick={() => setStockFilter('all')}>Все</button>
                  <button className={stockFilter === 'stored' ? 'selected' : ''} onClick={() => setStockFilter('stored')}>На хранении</button>
                  <button className={stockFilter === 'urgent' ? 'selected' : ''} onClick={() => setStockFilter('urgent')}>Скоро истекает</button>
                </div>
              </div>
              {renderStockTable()}
            </section>
          )}

          {tab === 'accruals' && (
            <>
              <section className="accrual-stats">
                <article className="stat-card">
                  <div className="stat-top"><span>Всего начислено</span><div className="stat-icon green"><Icon name="wallet" /></div></div>
                  <div className="stat-value">{money(totalAccrual)}</div>
                  <div className="stat-note">За всё время работы ПВЗ</div>
                </article>
                <article className="stat-card">
                  <div className="stat-top"><span>Количество операций</span><div className="stat-icon blue"><Icon name="trend" /></div></div>
                  <div className="stat-value">{accruals.length}<small> шт.</small></div>
                  <div className="stat-note">Все зафиксированные начисления</div>
                </article>
                <article className="stat-card">
                  <div className="stat-top"><span>Среднее начисление</span><div className="stat-icon violet"><Icon name="spark" /></div></div>
                  <div className="stat-value">{money(accruals.length ? totalAccrual / accruals.length : 0)}</div>
                  <div className="stat-note">На одну операцию</div>
                </article>
              </section>
              <section className="panel accrual-panel">
                <div className="panel-heading">
                  <div><h2>История начислений</h2><p>Все финансовые операции по пункту выдачи</p></div>
                  <span className="chart-period">{accruals.length} операций</span>
                </div>
                <div className="table-wrap">
                  <table className="data-table accrual-table">
                    <thead><tr><th>Операция</th><th>Дата и время</th><th>Связанный объект</th><th>Сумма</th></tr></thead>
                    <tbody>
                      {recentAccruals.map((item) => (
                        <tr key={item.id}>
                          <td><div className="accrual-name"><div className="activity-icon"><Icon name="wallet" size={16} /></div><strong>{accrualNames[item.type] || item.type}</strong></div></td>
                          <td>{dateTimeFormat(item.created_at)}</td>
                          <td><span className="muted">{item.order_id ? 'Заказ #' + item.order_id : item.stock_item_id ? 'Товар #' + item.stock_item_id : '—'}</span></td>
                          <td><strong className="positive-amount">+{money(item.amount)}</strong></td>
                        </tr>
                      ))}
                      {recentAccruals.length === 0 && <tr><td colSpan={4} className="empty-state">Начислений пока нет</td></tr>}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}

          <footer className="page-footer"><span>mesh. · Кабинет пункта выдачи</span><span>Данные обновляются при синхронизации <i /></span></footer>
        </div>
      </main>
    </div>
  );
}

export default App;
