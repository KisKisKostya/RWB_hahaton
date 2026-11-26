# Mesh MVP — checklist and demo guide for submission

## 1. Coverage of evaluation criteria

| Evaluation criterion | What is present in the prototype | How to demonstrate |
|---|---|---|
| End-to-end business processes | Intake, demand upload, automatic TOP-5, stock reservations, routes, transfers, pickup, returns, cancellations and incident handling | Follow the scenario below without changing database rows manually |
| Business processes exist in the MVP | Separate operator, seller and customer workspaces call backend API and persist changes in SQLite | Use the operator navigation, then switch to seller and customer |
| Financial model is inside the code | Storage tariff, local/hub transport formula, assembly/intake fees, seller-specific commission, PVZ accruals, refunds and seller payouts | Open "Финансовая модель"; complete a pickup and a return; refresh the report |
| Business logic follows the Mesh idea | Demand-first stock positioning, category and volume limits, road-graph pathfinding, truck-stop order and use of existing routes | Upload weekly demand, pass goods from seller and inspect the transfer queue |
| Communication and demonstrability | This guide plus seeded demo data and explicit edge-case scenarios | Present the 6–8 minute walkthrough below |

## 2. Run locally

Requirements: Python 3.12+, Node.js 22+, npm.

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --reload
```

Frontend, in a second terminal:

```powershell
cd frontend/pvz
npm ci
npm run dev
```

Open the local Vite URL printed in the terminal. The backend API documentation is available at `http://127.0.0.1:8000/docs`.

**Important:** `python -m app.seed` clears the demo tables before inserting fresh sample data. Run it only when you are ready to reset the local demo database. The application uses SQLite for this hackathon MVP.

## 3. Recommended 6–8 minute demonstration

### Part A — Operator: network and demand

1. Open **Карта сети** and show PVZ/warehouse points, Mesh participation, storage area and height.
2. Open **Дорожные рейсы**. Show the shortest road path and route stop sequence. Pause and reactivate a route to demonstrate route availability control.
3. Open **Спрос и TOP-5**. Select a PVZ and upload a weekly snapshot in the format `product_id,quantity`, one product per line. The backend stores the snapshot and recalculates TOP-5 and target stock from demand, dimensions and free storage volume.

### Part B — Seller: automatic allocation

1. Open **Поставки в Mesh**.
2. Select a seller and product, verify package dimensions, specify quantity and the PVZ where the seller physically brings the goods.
3. Submit the intake. Mesh chooses a demand PVZ or a hub, checks both the intake point and destination for unit and cubic-volume limits, records an intake accrual and places a transfer on an existing truck route when the destination differs.

### Part C — Customer: local availability and pickup

1. Open **Личный кабинет** and save a customer profile.
2. Search for a product around the preferred PVZ. Show the list of points where it is already available.
3. Create an order for an in-stock PVZ and confirm pickup. The exact stock batch is reserved, then issued; the reservation is released and PVZ accruals are written.

### Part D — Operator: return and exception handling

1. Open **Возвраты товаров**. Select the just-issued order and register an intact return. With available capacity, the goods return to the sellable stock. With no capacity, Mesh attempts to move them to a connected hub through an existing route.
2. Register a damaged return for another issued order. The item receives the non-sellable `DAMAGED` status and an open incident is created. Resolve that incident after confirming the item has been handed to the seller; all lots attached to that order are updated.
3. Open **Сбои и инциденты**. Report a route failure for a transfer. Pause the affected route in **Дорожные рейсы**, create or reactivate an alternative route with the correct stop order, then return to the incident screen and retry assignment. Once a compatible route is found, the incident is resolved.
4. Use the same screen to cancel an active order. Demonstrate that its capacity reservation is deleted and all reserved/assembled lots are restored to `STORED`.

### Part E — Finance

1. Open **Финансовая модель**.
2. Show gross sales, refunds, net sales, commission, storage fees, logistics costs, seller payout and PVZ accruals for the selected PVZ.
3. Filter seller payouts. Explain that each seller's own `commission_rate` is used.
4. Open **Начисления** to show the underlying entries, including negative return adjustments.

## 4. Financial assumptions used by the demo

The tariffs are example values for the prototype, not official Wildberries tariffs. They are kept in `backend/app/tariffs.py`.

| Component | Demo formula |
|---|---|
| Storage | `ceil(days in storage) × 5 ₽ × units` |
| Local route | `80 ₽ + 6 ₽ × road km + 20 ₽ assembly` |
| Hub route | `120 ₽ + 3.5 ₽ × road km + 40 ₽ processing` |
| Marketplace commission | Seller-specific percentage × net item sales |
| Seller payout | Net item sales − seller commission − storage |
| PVZ income | Intake, assembly, storage and local bonus accrual entries |
| Return | Negative refund adjustment equal to item price × returned quantity |

The financial summary is a transparent operating-model calculation based on the rows stored in the MVP database. It is not a payment processor, bank ledger or statutory accounting report.

## 5. Exception scenarios represented in the prototype

- **No suitable truck route:** transfer remains in `WAITING_ROUTE`; it is not dispatched as an independent vehicle.
- **Truck route cancelled or disabled:** assigned transfers are recalculated; those without a valid replacement return to the waiting queue and create an incident.
- **Insufficient capacity at destination:** transfer completion is rejected, goods remain in transit status and a capacity incident is persisted.
- **Order cancelled:** order moves to `CANCELLED`, capacity reservations are removed and stock reserved for the order is released.
- **Order delivery failure:** order moves to `FAILED_ROUTE`, reservations are released and an incident is created.
- **Intact return with no local capacity:** the return is queued for a Mesh transfer to a suitable connected hub; if there is no suitable hub/route, an open incident requires operator resolution.
- **Damaged return:** the item is removed from sellable stock and remains in the incident queue until the operator confirms handoff to the seller.
- **Duplicate return:** the API rejects a second return for the same order.

## 6. Important limitations to disclose

1. The operator, seller and customer windows are demo workspaces, not production authentication or role-based access control. The customer demo uses a seeded/default profile.
2. Geocoding, road distances and route stops are entered by the operator. Dijkstra computes a shortest path only over the road edges entered into this prototype; there is no live road-traffic or carrier API.
3. A transfer is completed by explicit operator confirmation. There is no truck GPS, proof-of-delivery integration or automatic carrier status feed.
4. A damaged item marked as sent to the seller is recorded after manual operator confirmation; an actual parcel shipment label or seller return service is not integrated.
5. The displayed tariffs/category size limits are sample assumptions and must be replaced with approved commercial/logistics values before real deployment.
6. Refunds and payouts are recorded as financial calculations and accrual corrections. The prototype does not execute card refunds or seller bank transfers.
7. SQLite and the local development setup are intended for a hackathon demo, not concurrent production traffic.

## 7. Technical structure

- **Frontend:** React, TypeScript, Vite.
- **Backend:** Python, FastAPI, Pydantic.
- **Persistence:** SQLAlchemy + SQLite, with lightweight SQLite schema migrations.
- **Demand and stock:** weekly demand snapshots, automatic TOP-5, package volume and storage constraints.
- **Routing:** road graph, Dijkstra shortest path, truck routes with ordered stops.
- **Operations:** exact stock-lot reservation, transfers, returns, cancellation, route/order incident log.
- **Finance:** tariff functions, seller-level commission, PVZ accruals, refund adjustments and seller payout summaries.
- **Quality gates:** backend pytest suite and frontend TypeScript/Vite production build in GitHub Actions.

## 8. Suggested final statement

"Mesh переносит часть товара ближе к подтверждённому локальному спросу. Система использует фактическую статистику продаж, ограничения ПВЗ и габариты упаковки, а перемещение выполняет только на существующих грузовых маршрутах. MVP охватывает путь от поставки продавца до выдачи покупателю, а также возвраты, отмены и нештатные ситуации. Финансовые последствия основных операций рассчитываются в backend. Сейчас это демонстрационный прототип: тарификация, авторизация и внешние транспортные/платёжные интеграции требуют промышленной настройки."
