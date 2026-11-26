const API_BASE = 'http://127.0.0.1:8000';

async function request(path: string, options?: RequestInit) {
  const response = await fetch(API_BASE + path, options);
  if (!response.ok) {
    let message = 'Ошибка запроса к серверу';
    try {
      const body = await response.json();
      message = typeof body.detail === 'string' ? body.detail : body.detail?.error || message;
    } catch {
      // Keep the fallback message when the response is not JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

export const api = {
  getCapacity: (pvzId: number) => request('/pvz/' + pvzId + '/capacity'),
  getStock: (pvzId: number) => request('/pvz/' + pvzId + '/stock'),
  getAccruals: (pvzId: number) => request('/pvz/' + pvzId + '/accruals'),
  getProducts: () => request('/products'),
  getPvz: () => request('/pvz'),
  intake: (pvzId: number, data: { product_id: number; qty: number; top_flag?: boolean }) =>
    request('/pvz/' + pvzId + '/intake', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),
  relocate: (stockId: number, data: { target_pvz_id: number; reason?: string }) =>
    request('/stock/' + stockId + '/relocate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),
};
