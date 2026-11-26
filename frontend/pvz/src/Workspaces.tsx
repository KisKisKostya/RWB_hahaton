import { useEffect, useState, type FormEvent, type MouseEvent, type ReactNode } from 'react';
import { api } from './api';
import './Workspaces.css';

type Location = {
  id: number;
  city: string;
  address: string;
  label?: string;
  is_hub?: boolean;
  is_mesh_enabled?: boolean;
  latitude?: number;
  longitude?: number;
  storage_area_m2?: number;
  storage_height_m?: number;
  storage_capacity_m3?: number;
  occupied_volume_m3?: number;
};

type Product = {
  id: number;
  name: string;
  sku: string;
  category: string;
  price: number;
  length_cm?: number;
  width_cm?: number;
  height_cm?: number;
};

type NetworkMap = { locations: Location[]; edges: any[] };
type Assortment = { top_products: any[]; candidates: any[]; storage_capacity_m3: number; occupied_volume_m3: number; free_volume_m3: number };
type WorkspaceProps = { selectedPvzId: number; pvzList: Location[]; onRefresh?: () => void };

const rub = (value: number) => new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(value || 0);
const jsonError = (error: unknown) => error instanceof Error ? error.message : 'Не удалось выполнить операцию';

function Panel({ title, subtitle, children, action }: { title: string; subtitle?: string; children: ReactNode; action?: React.ReactNode }) {
  return <section className="workspace-panel">
    <header className="workspace-panel-head">
      <div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
      {action}
    </header>
    {children}
  </section>;
}

function Message({ value, onClose }: { value: string; onClose: () => void }) {
  if (!value) return null;
  return <div className="workspace-message"><span>{value}</span><button onClick={onClose}>×</button></div>;
}

export function NetworkWorkspace({ pvzList }: WorkspaceProps) {
  const [map, setMap] = useState<NetworkMap>({ locations: [], edges: [] });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [form, setForm] = useState({
    city: 'Казань', address: '', type: 'pvz', is_mesh_enabled: true,
    latitude: '', longitude: '', storage_area_m2: '20', storage_height_m: '2.2',
  });
  const [edgeForm, setEdgeForm] = useState({ from_pvz_id: String(pvzList[0]?.id || ''), to_pvz_id: String(pvzList[1]?.id || ''), distance_km: '5' });
  const [mapPick, setMapPick] = useState(false);

  const load = async () => {
    try { setMap(await api.getNetworkMap()); } catch (error) { setMessage(jsonError(error)); }
  };
  useEffect(() => { load(); }, []);

  const bounds = useMemo(() => {
    if (!map.locations.length) return { minLat: 55.6, maxLat: 56, minLon: 48.8, maxLon: 49.4 };
    const lats = map.locations.map((node) => Number(node.latitude || 0));
    const lons = map.locations.map((node) => Number(node.longitude || 0));
    return {
      minLat: Math.min(...lats) - 0.04, maxLat: Math.max(...lats) + 0.04,
      minLon: Math.min(...lons) - 0.04, maxLon: Math.max(...lons) + 0.04,
    };
  }, [map.locations]);

  const point = (node: Location) => ({
    x: 80 + ((Number(node.longitude) - bounds.minLon) / Math.max(bounds.maxLon - bounds.minLon, 0.001)) * 740,
    y: 45 + ((bounds.maxLat - Number(node.latitude)) / Math.max(bounds.maxLat - bounds.minLat, 0.001)) * 280,
  });

  const pickCoordinates = (event: MouseEvent<SVGSVGElement>) => {
    if (!mapPick) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * 900;
    const y = ((event.clientY - rect.top) / rect.height) * 370;
    const longitude = bounds.minLon + ((x - 80) / 740) * (bounds.maxLon - bounds.minLon);
    const latitude = bounds.maxLat - ((y - 45) / 280) * (bounds.maxLat - bounds.minLat);
    setForm((current) => ({ ...current, latitude: latitude.toFixed(5), longitude: longitude.toFixed(5) }));
    setMapPick(false);
    setMessage('Координаты точки выбраны на карте.');
  };

  const createLocation = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      await api.createPvz({
        city: form.city, address: form.address, is_hub: form.type === 'hub',
        is_mesh_enabled: form.is_mesh_enabled,
        latitude: form.latitude ? Number(form.latitude) : null,
        longitude: form.longitude ? Number(form.longitude) : null,
        storage_area_m2: Number(form.storage_area_m2),
        storage_height_m: Number(form.storage_height_m),
      });
      setForm((current) => ({ ...current, address: '', latitude: '', longitude: '' }));
      setMessage(form.type === 'hub' ? 'Склад добавлен в сеть.' : 'Пункт выдачи добавлен в сеть.');
      await load();
    } catch (error) { setMessage(jsonError(error)); }
    finally { setBusy(false); }
  };

  const addEdge = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      await api.createEdge({ ...edgeForm, from_pvz_id: Number(edgeForm.from_pvz_id), to_pvz_id: Number(edgeForm.to_pvz_id), distance_km: Number(edgeForm.distance_km), bidirectional: true });
      setMessage('Дорога добавлена в граф. Доступные перемещения пересчитаны.');
      await load();
    } catch (error) { setMessage(jsonError(error)); }
    finally { setBusy(false); }
  };

  return <div className="workspace-stack">
    <Message value={message} onClose={() => setMessage('')} />
    <div className="workspace-intro"><div><span className="workspace-kicker">ОПЕРАТОР · ГЕОГРАФИЯ</span><h1>Сеть пунктов и складов</h1><p>Добавляйте точки, задавайте их координаты и связывайте дорожными рёбрами для расчёта маршрутов.</p></div><div className="workspace-mini-stats"><div><strong>{map.locations.filter((x) => !x.is_hub).length}</strong><span>ПВЗ</span></div><div><strong>{map.locations.filter((x) => x.is_hub).length}</strong><span>Склады</span></div><div><strong>{map.edges.length}</strong><span>Дорог</span></div></div></div>

    <Panel title="Карта сети Mesh" subtitle="Схематичная карта узлов. Нажмите «Выбрать точку на карте», затем кликните, чтобы задать координаты нового объекта.">
      <div className="network-map-toolbar"><span><i className="map-dot map-dot-pvz" /> Пункт выдачи <i className="map-dot map-dot-hub" /> Склад / хаб <i className="map-line" /> Дорога</span><button className={'workspace-button ' + (mapPick ? 'is-selected' : '')} onClick={() => setMapPick(!mapPick)}>{mapPick ? 'Отменить выбор точки' : 'Выбрать точку на карте'}</button></div>
      <div className={'network-map-canvas ' + (mapPick ? 'map-is-picking' : '')}>
        <svg viewBox="0 0 900 370" role="img" aria-label="Карта пунктов выдачи и складов" onClick={pickCoordinates}>
          <defs><pattern id="map-grid" width="34" height="34" patternUnits="userSpaceOnUse"><path d="M 34 0 L 0 0 0 34" fill="none" stroke="#e8edf3" strokeWidth="1" /></pattern></defs>
          <rect width="900" height="370" fill="url(#map-grid)" />
          <path d="M0 292 C180 235 215 355 390 258 S640 150 900 230" stroke="#d5e9e6" strokeWidth="22" fill="none" opacity=".55" />
          <path d="M-20 93 C120 145 225 105 310 155 S510 265 720 110 S850 85 930 125" stroke="#e7e1d7" strokeWidth="15" fill="none" opacity=".5" />
          {map.edges.map((edge) => {
            const from = map.locations.find((node) => node.id === edge.from_pvz_id);
            const to = map.locations.find((node) => node.id === edge.to_pvz_id);
            if (!from || !to) return null;
            const a = point(from), b = point(to);
            return <g key={edge.id}><line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#9ba7b9" strokeWidth="2.5" strokeDasharray="7 5" /><text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 7} fill="#748198" fontSize="11" textAnchor="middle">{edge.distance_km} км</text></g>;
          })}
          {map.locations.map((node) => {
            const p = point(node);
            return <g key={node.id} className="map-node">
              <circle cx={p.x} cy={p.y} r={node.is_hub ? 16 : 13} fill={node.is_hub ? '#1e2a43' : '#b31389'} stroke="#fff" strokeWidth="4" />
              <text x={p.x} y={p.y + 4} textAnchor="middle" fill="#fff" fontSize="11" fontWeight="700">{node.is_hub ? 'С' : 'П'}</text>
              <text x={p.x} y={p.y + 31} textAnchor="middle" fill="#30394d" fontSize="12" fontWeight="650">{node.city} · #{node.id}</text>
            </g>;
          })}
          {mapPick && <text x="450" y="25" textAnchor="middle" fill="#a10e7e" fontSize="13" fontWeight="700">Кликните в нужном месте карты</text>}
        </svg>
      </div>
      <div className="map-location-list">{map.locations.map((node) => <div key={node.id} className="map-location-item"><span className={'map-location-type ' + (node.is_hub ? 'hub' : '')}>{node.is_hub ? 'С' : 'П'}</span><div><strong>{node.city}, {node.address}</strong><small>{node.storage_capacity_m3} м³ · занято {node.occupied_volume_m3} м³</small></div><span className={node.is_mesh_enabled ? 'mesh-enabled' : 'mesh-disabled'}>{node.is_mesh_enabled ? 'Mesh включён' : 'Вне Mesh'}</span></div>)}</div>
    </Panel>

    <div className="workspace-two-col">
      <Panel title="Добавить ПВЗ или склад" subtitle="Новая точка сети и физические параметры хранения">
        <form className="workspace-form" onSubmit={createLocation}>
          <div className="workspace-form-grid">
            <label>Тип объекта<select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}><option value="pvz">Пункт выдачи</option><option value="hub">Склад / хаб</option></select></label>
            <label>Город<input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} required /></label>
            <label className="form-span-2">Адрес<input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} placeholder="Улица, дом" required /></label>
            <label>Широта<input type="number" step="any" value={form.latitude} onChange={(e) => setForm({ ...form, latitude: e.target.value })} placeholder="55.7903" /></label>
            <label>Долгота<input type="number" step="any" value={form.longitude} onChange={(e) => setForm({ ...form, longitude: e.target.value })} placeholder="49.1115" /></label>
            <label>Площадь хранения, м²<input type="number" step="0.1" min="0.1" value={form.storage_area_m2} onChange={(e) => setForm({ ...form, storage_area_m2: e.target.value })} required /></label>
            <label>Высота хранения, м<input type="number" step="0.1" min="0.1" value={form.storage_height_m} onChange={(e) => setForm({ ...form, storage_height_m: e.target.value })} required /></label>
          </div>
          <label className="workspace-check"><input type="checkbox" checked={form.is_mesh_enabled} onChange={(e) => setForm({ ...form, is_mesh_enabled: e.target.checked })} /> Участвует в системе Mesh-доставки</label>
          <button className="workspace-button primary" disabled={busy}>{busy ? 'Сохраняем…' : 'Добавить объект'}</button>
        </form>
      </Panel>
      <Panel title="Добавить дорожное ребро" subtitle="Расстояние между двумя точками учитывается алгоритмом Дейкстры">
        <form className="workspace-form" onSubmit={addEdge}>
          <label>Откуда<select value={edgeForm.from_pvz_id} onChange={(e) => setEdgeForm({ ...edgeForm, from_pvz_id: e.target.value })}>{map.locations.map((node) => <option value={node.id} key={node.id}>#{node.id} · {node.city}, {node.address}</option>)}</select></label>
          <label>Куда<select value={edgeForm.to_pvz_id} onChange={(e) => setEdgeForm({ ...edgeForm, to_pvz_id: e.target.value })}>{map.locations.map((node) => <option value={node.id} key={node.id}>#{node.id} · {node.city}, {node.address}</option>)}</select></label>
          <label>Длина дороги, км<input type="number" min="0.1" step="0.1" value={edgeForm.distance_km} onChange={(e) => setEdgeForm({ ...edgeForm, distance_km: e.target.value })} required /></label>
          <p className="workspace-help">Дорога добавляется как двусторонняя. Для одностороннего движения можно будет задать отдельное направление на следующем этапе.</p>
          <button className="workspace-button primary" disabled={busy || map.locations.length < 2}>Добавить дорогу</button>
        </form>
      </Panel>
    </div>
  </div>;
}

export function DemandWorkspace({ selectedPvzId }: WorkspaceProps) {
  const [raw, setRaw] = useState('1, 18\n2, 12\n3, 9\n4, 7\n5, 5');
  const [weekStart, setWeekStart] = useState(() => new Date().toISOString().slice(0, 10));
  const [assortment, setAssortment] = useState<Assortment | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  const load = async () => {
    try { setAssortment(await api.getAssortment(selectedPvzId)); }
    catch (error) { setMessage(jsonError(error)); }
  };
  useEffect(() => { load(); }, [selectedPvzId]);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    const rows = raw.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).map((line) => {
      const parts = line.split(/[;,\t]/).map((part) => part.trim());
      return { product_id: Number(parts[0]), quantity: Number(parts[1]) };
    }).filter((row) => Number.isInteger(row.product_id) && row.product_id > 0 && Number.isInteger(row.quantity) && row.quantity >= 0);
    if (!rows.length) { setMessage('Добавьте строки в формате: ID товара, количество за неделю.'); return; }
    setBusy(true);
    try {
      const result = await api.uploadDemand(selectedPvzId, { week_start: weekStart, rows });
      setAssortment(result.assortment);
      setMessage('Статистика сохранена. TOP-5 и потребность пересчитаны автоматически; создано перемещений: ' + result.planned_transfers.length + '.');
    } catch (error) { setMessage(jsonError(error)); }
    finally { setBusy(false); }
  };

  return <div className="workspace-stack">
    <Message value={message} onClose={() => setMessage('')} />
    <div className="workspace-intro"><div><span className="workspace-kicker">ОПЕРАТОР · СПРОС И ЗАПАСЫ</span><h1>Автоматический ассортимент</h1><p>Загружайте продажи за неделю пачкой. Mesh сам выбирает до пяти востребованных товаров с учётом габаритов и свободного объёма.</p></div></div>
    <div className="workspace-two-col demand-columns">
      <Panel title="Загрузить статистику за неделю" subtitle="Каждая строка — ID товара и проданное количество">
        <form className="workspace-form" onSubmit={save}>
          <label>Начало недели<input type="date" value={weekStart} onChange={(e) => setWeekStart(e.target.value)} required /></label>
          <label>Статистика покупок<textarea rows={8} value={raw} onChange={(e) => setRaw(e.target.value)} spellCheck={false} /></label>
          <p className="workspace-help">Формат CSV/TSV: <code>product_id, quantity</code>. Данные сохраняются в истории, а повторная загрузка за ту же неделю обновит соответствующие позиции.</p>
          <button className="workspace-button primary" disabled={busy}>{busy ? 'Сохраняем и пересчитываем…' : 'Сохранить статистику и пересчитать TOP'}</button>
        </form>
      </Panel>
      <Panel title="Объём хранения" subtitle="Свободная площадь переводится в объём с учётом высоты хранения">
        <div className="volume-summary">
          <div><span>Общий объём</span><strong>{assortment?.storage_capacity_m3 ?? '—'} м³</strong></div>
          <div><span>Занято товарами</span><strong>{assortment?.occupied_volume_m3 ?? '—'} м³</strong></div>
          <div><span>Свободно</span><strong className="volume-free">{assortment?.free_volume_m3 ?? '—'} м³</strong></div>
        </div>
        <div className="volume-bar"><i style={{ width: (assortment && assortment.storage_capacity_m3 ? Math.min(100, assortment.occupied_volume_m3 / assortment.storage_capacity_m3 * 100) : 0) + '%' }} /></div>
        <div className="policy-note"><strong>Правила автоподбора</strong><ul><li>TOP — максимум 5 товаров на ПВЗ.</li><li>Запас — средние продажи за 3 дня с учётом срока поставки.</li><li>Крупногабаритные упаковки более 0,08 м³ не размещаются.</li><li>Общий рекомендованный запас не превышает свободный объём.</li></ul></div>
      </Panel>
    </div>
    <Panel title="Топ товаров для выбранного ПВЗ" subtitle="Приоритет сформирован из истории продаж и физических габаритов. Ручного флага TOP больше нет.">
      <div className="assortment-list">
        {(assortment?.top_products || []).map((item: any) => <div className="assortment-row" key={item.product_id}>
          <span className="rank-number">{item.rank}</span>
          <div className="assortment-product"><strong>{item.name}</strong><small>{item.category} · {item.sku}</small></div>
          <div className="assortment-metric"><strong>{item.weekly_demand}</strong><small>продаж / нед.</small></div>
          <div className="assortment-metric"><strong>{item.volume_m3} м³</strong><small>объём единицы</small></div>
          <div className="assortment-qty"><strong>{item.allocatable_qty} шт.</strong><small>рекомендуемый запас</small></div>
        </div>)}
        {!assortment?.top_products?.length && <div className="workspace-empty">Пока нет статистики спроса. Загрузите недельный список покупок.</div>}
      </div>
    </Panel>
    <Panel title="Отклонённые товары" subtitle="Не попали в TOP из-за габаритов, спроса или нехватки объёма">
      <div className="candidate-list">{(assortment?.candidates || []).filter((item: any) => item.excluded_reason).slice(0, 8).map((item: any) => <div key={item.product_id}><span>{item.name}</span><small>{item.excluded_reason}</small></div>)}{!assortment?.candidates?.some((item: any) => item.excluded_reason) && <div className="workspace-empty">Нет отклонённых товаров.</div>}</div>
    </Panel>
  </div>;
}

export function RoutesWorkspace({ pvzList }: WorkspaceProps) {
  const [routes, setRoutes] = useState<any[]>([]);
  const [name, setName] = useState('Новый рейс');
  const [fromId, setFromId] = useState(String(pvzList[0]?.id || ''));
  const [toId, setToId] = useState(String(pvzList[1]?.id || ''));
  const [path, setPath] = useState<number[]>([]);
  const [distance, setDistance] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const locName = (id: number) => pvzList.find((node) => node.id === id)?.address || 'Пункт #' + id;
  const load = async () => { try { setRoutes(await api.listTruckRoutes()); } catch (error) { setMessage(jsonError(error)); } };
  useEffect(() => { load(); }, []);

  const calculate = async () => {
    setBusy(true);
    try {
      const result = await api.shortestPath(Number(fromId), Number(toId));
      setPath(result.path);
      setDistance(result.distance_km);
      setMessage('Кратчайший путь рассчитан алгоритмом Дейкстры.');
    } catch (error) { setPath([]); setDistance(null); setMessage(jsonError(error)); }
    finally { setBusy(false); }
  };

  const saveRoute = async () => {
    if (path.length < 2) return;
    setBusy(true);
    try {
      await api.createTruckRoute({ name, stop_pvz_ids: path, is_active: true });
      setMessage('Активный рейс сохранён. Ожидающие перемещения проверены на совместимость.');
      setPath([]); setDistance(null); await load();
    } catch (error) { setMessage(jsonError(error)); }
    finally { setBusy(false); }
  };

  return <div className="workspace-stack">
    <Message value={message} onClose={() => setMessage('')} />
    <div className="workspace-intro"><div><span className="workspace-kicker">ОПЕРАТОР · ЛОГИСТИКА</span><h1>Дорожная сеть и рейсы</h1><p>Задавайте последовательность остановок грузовиков и используйте кратчайшие дороги для расчёта расстояния.</p></div></div>
    <div className="workspace-two-col">
      <Panel title="Построить рейс" subtitle="Система подбирает кратчайший путь по дорожному графу">
        <div className="workspace-form">
          <label>Название рейса<input value={name} onChange={(e) => setName(e.target.value)} /></label>
          <div className="workspace-form-grid">
            <label>Начальная точка<select value={fromId} onChange={(e) => setFromId(e.target.value)}>{pvzList.map((node) => <option key={node.id} value={node.id}>#{node.id} · {node.city} · {node.address}</option>)}</select></label>
            <label>Конечная точка<select value={toId} onChange={(e) => setToId(e.target.value)}>{pvzList.map((node) => <option key={node.id} value={node.id}>#{node.id} · {node.city} · {node.address}</option>)}</select></label>
          </div>
          <button className="workspace-button" onClick={calculate} disabled={busy || !fromId || !toId || fromId === toId}>Рассчитать кратчайший путь</button>
          {path.length > 0 && <div className="route-result"><div><span>Длина по дорогам</span><strong>{distance} км</strong></div><div className="route-stops">{path.map((id, index) => <span key={id}>{index > 0 && <b>→</b>}<i>{index + 1}</i>{locName(id)}</span>)}</div><button className="workspace-button primary" onClick={saveRoute} disabled={busy}>Сохранить как действующий рейс</button></div>}
        </div>
      </Panel>
      <Panel title="Как строятся перемещения" subtitle="Учитывается порядок остановок в одном грузовом рейсе">
        <div className="route-explain">
          <div><span>01</span><div><strong>Точка отправления</strong><p>Машина забирает товар с ПВЗ или со склада, куда его принёс продавец.</p></div></div>
          <div><span>02</span><div><strong>Дорожный граф</strong><p>Дейкстра вычисляет кратчайшее расстояние по введённым дорогам, а не по прямой.</p></div></div>
          <div><span>03</span><div><strong>Точка назначения</strong><p>Товар можно доставить только если остановка назначения следует после отправления в действующем рейсе.</p></div></div>
        </div>
      </Panel>
    </div>
    <Panel title="Действующие маршруты" subtitle="Перемещения назначаются в рейс только при соблюдении порядка остановок">
      <div className="route-list">
        {routes.map((route) => <div className="route-list-row" key={route.id}><span className="route-icon">↗</span><div><strong>{route.name}</strong><small>{route.stop_pvz_ids.map((id: number) => '#' + id + ' ' + locName(id)).join(' → ')}</small></div><div className="assortment-metric"><strong>{route.distance_km ?? '—'} км</strong><small>по дорогам</small></div><span className={route.is_active ? 'route-active' : 'route-inactive'}>{route.is_active ? 'Активен' : 'Остановлен'}</span></div>)}
        {!routes.length && <div className="workspace-empty">Маршруты ещё не добавлены.</div>}
      </div>
    </Panel>
  </div>;
}

export function TransfersWorkspace(_: WorkspaceProps) {
  const [transfers, setTransfers] = useState<any[]>([]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [message, setMessage] = useState('');
  const load = async () => { try { setTransfers(await api.listTransfers()); } catch (error) { setMessage(jsonError(error)); } };
  useEffect(() => { load(); }, []);
  const finish = async (id: number) => {
    setBusyId(id);
    try { await api.completeTransfer(id); setMessage('Перемещение завершено, остатки ПВЗ пересчитаны.'); await load(); }
    catch (error) { setMessage(jsonError(error)); }
    finally { setBusyId(null); }
  };
  return <div className="workspace-stack">
    <Message value={message} onClose={() => setMessage('')} />
    <div className="workspace-intro"><div><span className="workspace-kicker">ОПЕРАТОР · ПЕРЕБАЛАНСИРОВКА</span><h1>Перемещения запасов</h1><p>Mesh ищет нуждающиеся ПВЗ и назначает перевозку на существующие рейсы. Если спроса нет — товар отправляется на хаб.</p></div><button className="workspace-button" onClick={load}>Обновить список</button></div>
    <Panel title="Очередь перемещений" subtitle="Товар физически меняет ПВЗ только после подтверждения доставки">
      <div className="transfer-list">
        {transfers.map((item) => <div className="transfer-card" key={item.id}>
          <div className="transfer-card-head"><div><strong>{item.product_name}</strong><small>{item.qty} шт. · {item.reason === 'no_local_demand' ? 'Нет локального спроса' : item.reason === 'seller_auto_intake' ? 'Автоприёмка продавца' : 'Изменение спроса'}</small></div><span className={item.status === 'READY_ON_ROUTE' ? 'transfer-ready' : item.status === 'COMPLETED' ? 'transfer-done' : 'transfer-wait'}>{item.status === 'READY_ON_ROUTE' ? 'В действующем рейсе' : item.status === 'COMPLETED' ? 'Доставлено' : 'Ожидает рейс'}</span></div>
          <div className="transfer-path"><div><small>Откуда</small><strong>{item.from_label}</strong></div><b>→</b><div><small>Куда</small><strong>{item.to_label}</strong></div></div>
          <div className="transfer-card-foot"><span>{item.route_name ? 'Рейс: ' + item.route_name : 'Маршрут пока не найден'} · {item.distance_km ? item.distance_km + ' км' : '—'}</span>{item.status === 'READY_ON_ROUTE' && <button className="workspace-button primary small" disabled={busyId === item.id} onClick={() => finish(item.id)}>{busyId === item.id ? 'Подтверждаем…' : 'Подтвердить доставку'}</button>}</div>
        </div>)}
        {!transfers.length && <div className="workspace-empty">Новых перемещений нет. После загрузки статистики Mesh создаст задачи автоматически.</div>}
      </div>
    </Panel>
  </div>;
}

export function SellerWorkspace({ pvzList }: WorkspaceProps) {
  const [products, setProducts] = useState<Product[]>([]);
  const [productId, setProductId] = useState('');
  const [qty, setQty] = useState('10');
  const [dimensions, setDimensions] = useState({ length_cm: '10', width_cm: '10', height_cm: '10' });
  const [originId, setOriginId] = useState(String(pvzList[0]?.id || ''));
  const [result, setResult] = useState<any>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.getProducts().then(setProducts).catch((error) => setMessage(jsonError(error))); }, []);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setResult(null);
    try {
      await api.updateProductDimensions(Number(productId), {
        length_cm: Number(dimensions.length_cm),
        width_cm: Number(dimensions.width_cm),
        height_cm: Number(dimensions.height_cm),
      });
      const response = await api.sellerIntake({ product_id: Number(productId), qty: Number(qty), origin_pvz_id: Number(originId) });
      setResult(response);
      setMessage('Система выбрала место хранения автоматически.');
    } catch (error) { setMessage(jsonError(error)); }
    finally { setBusy(false); }
  };
  return <div className="workspace-stack">
    <Message value={message} onClose={() => setMessage('')} />
    <div className="workspace-intro"><div><span className="workspace-kicker">КАБИНЕТ ПРОДАВЦА</span><h1>Поставка товаров в Mesh</h1><p>Привезите товар в удобный пункт. Система сама определит, где его выгоднее хранить — на ПВЗ с реальным спросом или на центральном хабе.</p></div></div>
    <div className="seller-workspace-grid">
      <Panel title="Передать товар в сеть" subtitle="Не нужно самостоятельно выбирать склад назначения">
        <form className="workspace-form" onSubmit={submit}>
          <label>Товар<select value={productId} onChange={(e) => {
            const value = e.target.value;
            const selected = products.find((item) => item.id === Number(value));
            setProductId(value);
            if (selected) setDimensions({
              length_cm: String(selected.length_cm || 10),
              width_cm: String(selected.width_cm || 10),
              height_cm: String(selected.height_cm || 10),
            });
          }} required><option value="">Выберите товар</option>{products.map((product) => <option key={product.id} value={product.id}>{product.name} · {product.sku}</option>)}</select></label>
          {productId && <div className="workspace-form-grid dimension-fields">
            <label>Длина, см<input type="number" min="0.1" step="0.1" value={dimensions.length_cm} onChange={(e) => setDimensions({ ...dimensions, length_cm: e.target.value })} required /></label>
            <label>Ширина, см<input type="number" min="0.1" step="0.1" value={dimensions.width_cm} onChange={(e) => setDimensions({ ...dimensions, width_cm: e.target.value })} required /></label>
            <label>Высота, см<input type="number" min="0.1" step="0.1" value={dimensions.height_cm} onChange={(e) => setDimensions({ ...dimensions, height_cm: e.target.value })} required /></label>
            <div className="product-size-preview"><strong>Объём единицы</strong><span>{((Number(dimensions.length_cm) * Number(dimensions.width_cm) * Number(dimensions.height_cm)) / 1000000).toFixed(4)} м³</span></div>
          </div>}
          <label>Количество, шт.<input type="number" min="1" value={qty} onChange={(e) => setQty(e.target.value)} required /></label>
          <label>Пункт, куда продавец привёз товар<select value={originId} onChange={(e) => setOriginId(e.target.value)} required>{pvzList.map((node) => <option value={node.id} key={node.id}>#{node.id} · {node.city}, {node.address}</option>)}</select></label>
          <div className="seller-auto-note"><span>✦</span><p><strong>Автоматическое распределение</strong> Приоритет получает пункт с наибольшими продажами этого товара, если хватает места. Крупногабаритные и невостребованные позиции направляются на хаб.</p></div>
          <button className="workspace-button primary" disabled={busy || !productId}>{busy ? 'Рассчитываем…' : 'Передать товар в Mesh'}</button>
        </form>
      </Panel>
      <div className="seller-benefits">
        <div className="seller-benefit"><span>01</span><strong>Анализ спроса</strong><p>Сравниваем недельные продажи товара на всех подключённых ПВЗ.</p></div>
        <div className="seller-benefit"><span>02</span><strong>Проверка габаритов</strong><p>Проверяем объём упаковки и доступный объём хранения на ПВЗ.</p></div>
        <div className="seller-benefit"><span>03</span><strong>Доставка попутным рейсом</strong><p>Если назначен другой ПВЗ, товар поедет в фуре по существующему маршруту.</p></div>
      </div>
    </div>
    {result && <Panel title="Решение Mesh" subtitle="Система сохранила приёмку и выбрала точку назначения">
      <div className="seller-decision">
        <div className="decision-check">✓</div><div><span>РЕКОМЕНДУЕМОЕ МЕСТО ХРАНЕНИЯ</span><strong>{result.destination}</strong><small>{result.storage_type === 'HUB' ? 'Центральный склад · хаб' : 'Пункт выдачи с подтверждённым спросом'}</small></div>
        <div className="decision-status">{result.transfer_status === 'READY_ON_ROUTE' ? 'Назначен рейс' : result.transfer_status === 'STORED_AT_DESTINATION' ? 'Остался на точке' : 'Ожидает рейс'}</div>
      </div>
      <p className="workspace-result-note">{result.explanation}</p>
    </Panel>}
  </div>;
}

export function CustomerWorkspace({ pvzList }: WorkspaceProps) {
  const [products, setProducts] = useState<Product[]>([]);
  const [profile, setProfile] = useState<any>({ name: '', phone: '', email: '', city: '', preferred_pvz_id: '' });
  const [orders, setOrders] = useState<any[]>([]);
  const [productId, setProductId] = useState('');
  const [pickupId, setPickupId] = useState('');
  const [radius, setRadius] = useState('25');
  const [availability, setAvailability] = useState<any>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const customerId = 1;
  useEffect(() => {
    Promise.all([api.getProducts(), api.getCustomerProfile(customerId), api.getCustomerOrders(customerId)])
      .then(([items, customer, customerOrders]) => {
        setProducts(items);
        setProfile({ ...customer, preferred_pvz_id: String(customer.preferred_pvz_id || '') });
        setPickupId(String(customer.preferred_pvz_id || pvzList[0]?.id || ''));
        setOrders(customerOrders);
      }).catch((error) => setMessage(jsonError(error)));
  }, []);
  const saveProfile = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true);
    try { await api.updateCustomerProfile(customerId, { ...profile, preferred_pvz_id: Number(profile.preferred_pvz_id) || null }); setMessage('Профиль покупателя сохранён.'); }
    catch (error) { setMessage(jsonError(error)); }
    finally { setBusy(false); }
  };
  const check = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setAvailability(null);
    try { setAvailability(await api.customerAvailability(Number(productId), Number(pickupId), Number(radius))); }
    catch (error) { setMessage(jsonError(error)); }
    finally { setBusy(false); }
  };
  const confirmPickup = async (orderId: number) => {
    setBusy(true);
    try {
      await api.confirmCustomerPickup(orderId, customerId);
      setMessage('Получение заказа #' + orderId + ' подтверждено.');
      setOrders(await api.getCustomerOrders(customerId));
    } catch (error) { setMessage(jsonError(error)); }
    finally { setBusy(false); }
  };
  const orderHere = async (locationId: number) => {
    setBusy(true);
    try {
      const response = await api.createCustomerOrder({ product_id: Number(productId), qty: 1, buyer_pvz_id: locationId }, customerId);
      setMessage('Заказ #' + response.id + ' оформлен. ' + response.pickup_address);
      setOrders(await api.getCustomerOrders(customerId));
    } catch (error) { setMessage(jsonError(error)); }
    finally { setBusy(false); }
  };
  return <div className="workspace-stack">
    <Message value={message} onClose={() => setMessage('')} />
    <div className="workspace-intro"><div><span className="workspace-kicker">ЛИЧНЫЙ КАБИНЕТ ПОКУПАТЕЛЯ</span><h1>Ваши покупки и пункты выдачи</h1><p>Выбирайте ближайший ПВЗ. Если товар уже есть в соседнем пункте, Mesh покажет, где его можно забрать прямо сейчас.</p></div></div>
    <div className="customer-workspace-grid">
      <Panel title="Профиль покупателя" subtitle="Контактные данные и пункт выдачи по умолчанию">
        <form className="workspace-form" onSubmit={saveProfile}>
          <label>Имя<input value={profile.name || ''} onChange={(e) => setProfile({ ...profile, name: e.target.value })} required /></label>
          <label>Телефон<input value={profile.phone || ''} onChange={(e) => setProfile({ ...profile, phone: e.target.value })} placeholder="+7 ___ ___-__-__" /></label>
          <label>E-mail<input type="email" value={profile.email || ''} onChange={(e) => setProfile({ ...profile, email: e.target.value })} placeholder="mail@example.ru" /></label>
          <label>Город<input value={profile.city || ''} onChange={(e) => setProfile({ ...profile, city: e.target.value })} /></label>
          <label>Мой ПВЗ<select value={profile.preferred_pvz_id || ''} onChange={(e) => { setProfile({ ...profile, preferred_pvz_id: e.target.value }); setPickupId(e.target.value); }}><option value="">Выберите пункт</option>{pvzList.filter((node) => !node.is_hub).map((node) => <option key={node.id} value={node.id}>{node.city}, {node.address}</option>)}</select></label>
          <button className="workspace-button primary" disabled={busy}>Сохранить профиль</button>
        </form>
      </Panel>
      <div className="customer-find-column">
        <Panel title="Найти товар рядом" subtitle="Проверка наличия на выбранном ПВЗ и поблизости">
          <form className="workspace-form" onSubmit={check}>
            <label>Какой товар ищем?<select value={productId} onChange={(e) => setProductId(e.target.value)} required><option value="">Выберите товар</option>{products.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}</select></label>
            <label>Мой пункт выдачи<select value={pickupId} onChange={(e) => setPickupId(e.target.value)} required>{pvzList.filter((node) => !node.is_hub).map((node) => <option key={node.id} value={node.id}>#{node.id} · {node.city}, {node.address}</option>)}</select></label>
            <label>Радиус поиска, км<input type="number" min="1" max="300" value={radius} onChange={(e) => setRadius(e.target.value)} /></label>
            <button className="workspace-button primary" disabled={busy || !productId}>Проверить наличие</button>
          </form>
        </Panel>
        {availability && <Panel title={availability.available_at_selected ? 'Товар есть в вашем ПВЗ' : 'Можно забрать в другом пункте'} subtitle={availability.product_name}>
          <div className="pickup-options">
            {availability.pickup_options.map((option: any) => <div key={option.pvz_id} className="pickup-option">
              <div className="pickup-option-icon">{option.is_selected ? '⌂' : '↗'}</div>
              <div><strong>{option.city}, {option.address}</strong><small>{option.is_selected ? 'Ваш пункт выдачи' : option.distance_km + ' км от вашего ПВЗ'} · В наличии {option.qty} шт.</small></div>
              <button disabled={busy} onClick={() => orderHere(option.pvz_id)}>{option.is_selected ? 'Забрать здесь' : 'Забрать сейчас'}</button>
            </div>)}
            {!availability.pickup_options.length && <div className="workspace-empty">Товар не найден в выбранном радиусе.</div>}
          </div>
        </Panel>}
      </div>
    </div>
    <Panel title="Мои заказы" subtitle="История заказов в сети Mesh">
      <div className="customer-orders">{orders.map((order) => <div key={order.id}><span className="customer-order-id">#{order.id}</span><div><strong>Товар #{order.product_id} · {order.qty} шт.</strong><small>ПВЗ #{order.buyer_pvz_id} · {new Date(order.created_at).toLocaleDateString('ru-RU')}</small></div><span className="order-status">{order.status === 'READY' ? 'Готов к выдаче' : order.status === 'ISSUED' ? 'Получен' : order.status}</span>{order.status === 'READY' && <button className="workspace-button primary small" disabled={busy} onClick={() => confirmPickup(order.id)}>Подтвердить получение</button>}</div>)}{!orders.length && <div className="workspace-empty">Здесь появятся ваши заказы.</div>}</div>
    </Panel>
  </div>;
}
