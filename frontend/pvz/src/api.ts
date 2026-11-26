const API_BASE = 'http://127.0.0.1:8000';

export const api = {
  getCapacity: async (pvzId: number) => {
    const res = await fetch(`${API_BASE}/pvz/${pvzId}/capacity`);
    if (!res.ok) throw new Error('Ошибка загрузки ёмкости');
    return res.json();
  },
  getStock: async (pvzId: number) => {
    const res = await fetch(`${API_BASE}/pvz/${pvzId}/stock`);
    if (!res.ok) throw new Error('Ошибка загрузки остатков');
    return res.json();
  },
  getAccruals: async (pvzId: number) => {
    const res = await fetch(`${API_BASE}/pvz/${pvzId}/accruals`);
    if (!res.ok) throw new Error('Ошибка загрузки начислений');
    return res.json();
  },
  intake: async (pvzId: number, data: { product_id: number; qty: number; top_flag?: boolean }) => {
    const res = await fetch(`${API_BASE}/pvz/${pvzId}/intake`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Ошибка приёмки');
    return res.json();
  },
  relocate: async (stockId: number, data: { target_pvz_id: number; reason?: string }) => {
    const res = await fetch(`${API_BASE}/stock/${stockId}/relocate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Ошибка перемещения');
    return res.json();
  },
};