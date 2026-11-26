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
  getSellers: () => request('/sellers'),
  getSellerProducts: (sellerId: number) => request('/seller/' + sellerId + '/products'),
  getPvz: () => request('/pvz'),
  getNetworkMap: () => request('/network/map'),
  createPvz: (data: unknown) => request('/network/pvz', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  updatePvz: (id: number, data: unknown) => request('/network/pvz/' + id, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  listEdges: () => request('/network/edges'),
  createEdge: (data: unknown) => request('/network/edges', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  shortestPath: (fromId: number, toId: number) => request('/network/shortest-path?from_pvz_id=' + fromId + '&to_pvz_id=' + toId),
  listTruckRoutes: () => request('/network/routes'),
  createTruckRoute: (data: unknown) => request('/network/routes', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  getDemandHistory: (pvzId: number) => request('/network/demand/' + pvzId),
  uploadDemand: (pvzId: number, data: unknown) => request('/network/demand/' + pvzId, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  getAssortment: (pvzId: number) => request('/network/assortment/' + pvzId),
  listTransfers: () => request('/network/transfers'),
  completeTransfer: (id: number) => request('/network/transfers/' + id + '/complete', { method: 'POST' }),
  updateProductDimensions: (id: number, data: unknown) => request('/products/' + id + '/dimensions', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  sellerIntake: (data: unknown) => request('/seller/intake', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  getCustomerProfile: (id: number) => request('/customer/profile/' + id),
  updateCustomerProfile: (id: number, data: unknown) => request('/customer/profile/' + id, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  customerAvailability: (productId: number, pvzId: number, radiusKm: number) => request('/customer/availability?product_id=' + productId + '&pvz_id=' + pvzId + '&radius_km=' + radiusKm),
  createCustomerOrder: (data: unknown, customerId = 1) => request('/customer/orders?customer_id=' + customerId, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  getOrders: () => request('/orders'),
  createReturn: (orderId: number, data: { reason: string; condition: 'intact' | 'damaged' }) =>
    request('/orders/' + orderId + '/return', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  getReturns: () => request('/returns'),
  getIncidents: () => request('/ops/incidents'),
  reportTransferFailure: (id: number, message: string) =>
    request('/network/transfers/' + id + '/report-failure?message=' + encodeURIComponent(message), { method: 'POST' }),
  retryTransfer: (id: number) => request('/network/transfers/' + id + '/retry', { method: 'POST' }),
  resolveIncident: (id: number, data: { resolution_note: string; mark_sent_to_seller?: boolean }) =>
    request('/ops/incidents/' + id + '/resolve', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  cancelOrder: (id: number) => request('/orders/' + id + '/cancel', { method: 'POST' }),
  failOrder: (id: number, message: string) =>
    request('/orders/' + id + '/fail?message=' + encodeURIComponent(message), { method: 'POST' }),
  getFinanceSummary: (pvzId?: number) => request('/finance/summary' + (pvzId ? '?pvz_id=' + pvzId : '')),
  getFinanceSellerPayouts: () => request('/finance/seller-payouts'),
  getCustomerOrders: (id: number) => request('/customer/orders/' + id),
  confirmCustomerPickup: (orderId: number, customerId = 1) => request('/customer/orders/' + orderId + '/pickup?customer_id=' + customerId, { method: 'POST' }),
  intake: (pvzId: number, data: { product_id: number; qty: number }) =>
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
