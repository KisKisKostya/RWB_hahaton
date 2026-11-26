import { useState, useEffect } from 'react';
import { api } from './api';
import './App.css';

// ID вашего ПВЗ из seed-данных. Поменяйте при необходимости.
const CURRENT_PVZ_ID = 1;

function App() {
  const [tab, setTab] = useState<'dash' | 'intake' | 'stock' | 'accruals'>('dash');
  const [capacity, setCapacity] = useState<any>(null);
  const [stock, setStock] = useState<any[]>([]);
  const [accruals, setAccruals] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [cap, st, acc] = await Promise.all([
        api.getCapacity(CURRENT_PVZ_ID),
        api.getStock(CURRENT_PVZ_ID),
        api.getAccruals(CURRENT_PVZ_ID),
      ]);
      setCapacity(cap);
      setStock(st);
      setAccruals(acc);
    } catch (e: any) {
      setError(e.message || 'Ошибка загрузки данных');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleIntake = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    try {
      await api.intake(CURRENT_PVZ_ID, {
        product_id: Number(form.get('product_id')),
        qty: Number(form.get('qty')),
        top_flag: form.get('top_flag') === 'on',
      });
      e.currentTarget.reset();
      loadData();
    } catch (err: any) {
      alert(err.message);
    }
  };

  return (
    <div style={{ fontFamily: 'sans-serif', padding: '20px', maxWidth: '900px', margin: '0 auto' }}>
      <h1>Кабинет ПВЗ</h1>

      {loading && <p>Загрузка...</p>}
      {error && <p style={{ color: 'red' }}>{error}</p>}

      <div style={{ display: 'flex', gap: '10px', marginBottom: '20px', flexWrap: 'wrap' }}>
        <button onClick={() => setTab('dash')}>Дашборд</button>
        <button onClick={() => setTab('intake')}>Приёмка</button>
        <button onClick={() => setTab('stock')}>Хранение</button>
        <button onClick={() => setTab('accruals')}>Начисления</button>
      </div>

      <hr />

      {tab === 'dash' && (
        <div>
          <h2>Ёмкость и доход</h2>
          {capacity ? (
            <div style={{ padding: '20px', background: '#f0f0f0', borderRadius: '8px' }}>
              <p><b>Занято:</b> {capacity.occupied} / {capacity.capacity_units}</p>
              <p><b>Свободно:</b> {capacity.free}</p>
              <p><b>Товаров с истекающим TTL (меньше 2 дней):</b> {stock.filter(s => s.ttl_days < 2 && s.status === 'STORED').length}</p>
            </div>
          ) : <p>Нет данных</p>}
        </div>
      )}

      {tab === 'intake' && (
        <div>
          <h2>Приёмка товара</h2>
          <form onSubmit={handleIntake} style={{ display: 'flex', gap: '10px', flexDirection: 'column', maxWidth: '300px' }}>
            <input name="product_id" type="number" placeholder="ID товара" required />
            <input name="qty" type="number" placeholder="Количество" required min={1} />
            <label><input name="top_flag" type="checkbox" /> Топовая позиция</label>
            <button type="submit">Принять</button>
          </form>
        </div>
      )}

      {tab === 'stock' && (
        <div>
          <h2>Хранение</h2>
          <table border={1} cellPadding={10} style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr><th>ID</th><th>Товар</th><th>Кол-во</th><th>Статус</th><th>TTL (дней)</th><th>Действие</th></tr>
            </thead>
            <tbody>
              {stock.map(item => (
                <tr key={item.id}>
                  <td>{item.id}</td>
                  <td>{item.product_id}</td>
                  <td>{item.qty}</td>
                  <td>{item.status}</td>
                  <td style={{ color: item.ttl_days < 2 ? 'red' : 'black' }}>{item.ttl_days}</td>
                  <td>
                    {item.status === 'STORED' && (
                      <button onClick={() => api.relocate(item.id, { target_pvz_id: 2, reason: 'manual' }).then(loadData)}>
                        Переместить
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'accruals' && (
        <div>
          <h2>Начисления</h2>
          <table border={1} cellPadding={10} style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr><th>Дата</th><th>Тип</th><th>Сумма (руб)</th></tr>
            </thead>
            <tbody>
              {accruals.map((acc, i) => (
                <tr key={i}>
                  <td>{new Date(acc.created_at).toLocaleDateString()}</td>
                  <td>{acc.type}</td>
                  <td>{acc.amount}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default App;