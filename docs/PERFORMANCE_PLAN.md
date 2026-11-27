# TAnalytic: план оптимизации производительности

Составлен 27.11.2026. Текущее состояние: v0.31, сервер — Python `ThreadingHTTPServer` + SQLite WAL, `market_worker.py` + `/v1/market/snapshot` уже реализованы.

---

## 0. Что уже хорошо (не трогаем)

- `ThreadingHTTPServer` — параллельные запросы от разных клиентов не блокируют друг друга ✅
- `protocol_version = "HTTP/1.1"` — keep-alive есть ✅
- Singleflight (`_flights`) — 50 клиентов не дёргают MOEX одновременно за одной бумагой ✅
- SQLite `WAL` + `synchronous=NORMAL` ✅
- In-memory `_pcache` (LRU-500 для `/v1/proxy`) ✅
- `market_worker.py` + `/v1/market/snapshot` — готовый снэпшот рынка ✅
- SWR (stale-while-revalidate): горячий ответ + фоновое обновление ✅

---

## 1. 1 ядро или 2? Когда переходить

### Сейчас (до 100 активных пользователей): **1 ядра хватает**

Python GIL не мешает `ThreadingHTTPServer`, пока большинство потоков ждут I/O (сеть, SQLite). CPU занят <<10% времени.

### Когда переходить на 2 ядра:

| Сигнал | Означает |
|---|---|
| `top` показывает >60–70% CPU на `python3` в неторговое время | фоновые воркеры воруют время у HTTP |
| Латентность `/v1/proxy` растёт при активной работе `disclosure_worker` | GIL-конкуренция |
| >100 уникальных пользователей за 15 минут | пора |

**На 2 ядрах:** вынести `tinvest_server.py` и `tinvest-bot` в отдельные systemd-сервисы (они уже независимые процессы — просто добавить `CPUAffinity` или поднять на 2 ядрах).

---

## 2. Быстрые улучшения (S-размер, 1–2 часа каждое)

### 2.1 gzip-сжатие ответов

**Где:** `server/tinvest_server.py` → `_send_json()` и `/v1/market/snapshot`  
**Что сейчас:** JSON отдаётся без сжатия  
**Ожидаемый эффект:** снэпшот облигаций (~500–800 КБ JSON) → 80–120 КБ, x5–8 быстрее на мобильном/медленном канале  
**Как:**
```python
import gzip as gzip_mod

def _send_json(self, code, obj, extra_headers=None):
    body = json.dumps(obj, ensure_ascii=False).encode()
    ae = self.headers.get("Accept-Encoding", "")
    if "gzip" in ae and len(body) > 1400:
        body = gzip_mod.compress(body, compresslevel=5)
        hdrs = {"Content-Encoding": "gzip"}
    else:
        hdrs = {}
    if extra_headers:
        hdrs.update(extra_headers)
    self.send_response(code)
    for k, v in hdrs.items():
        self.send_header(k, v)
    self.send_header("Content-Type", "application/json; charset=utf-8")
    self.send_header("Content-Length", str(len(body)))
    self.end_headers()
    self.wfile.write(body)
```
**Тест:** `curl -H 'Accept-Encoding: gzip' -s -o /dev/null -w '%{size_download} %{time_total}\n' https://.../v1/market/snapshot`

---

### 2.2 ETag / 304 Not Modified для снэпшота и `/v1/proxy`

**Где:** `server/tinvest_server.py` → `/v1/market/snapshot`, `/v1/proxy`, `/v1/parsed/*`  
**Что сейчас:** клиент всегда получает полный JSON, даже если данные не изменились  
**Ожидаемый эффект:** в неторговое время (ночь, выходные) >90% запросов получат пустой `304` за 1–2 мс вместо 50–300 мс  
**Как:**
```python
# При отдаче снэпшота/кэша:
etag = f'"{hashlib.md5(body).hexdigest()[:12]}"'
if self.headers.get("If-None-Match") == etag:
    self.send_response(304)
    self.send_header("ETag", etag)
    self.end_headers()
    return
# иначе добавляем ETag в заголовок ответа
```
**Клиент** (`src/py/12_ext_open.py`): при 304 брать данные из локального кэша.

---

### 2.3 SQLite: `mmap_size` + `cache_size` + пул соединений

**Где:** `CacheStore.__init__()` в `server/tinvest_server.py`  
**Что сейчас:** `WAL + synchronous=NORMAL`, один `Connection` + лок  
**Ожидаемый эффект:** снижение latency чтения кэша на нагруженном сервере  
**Как:**
```python
self.db.execute("PRAGMA mmap_size=134217728")   # 128 МБ mmap-чтения без GIL
self.db.execute("PRAGMA cache_size=-32768")      # 32 МБ page cache
self.db.execute("PRAGMA temp_store=MEMORY")
```
Также: для read-only запросов к `snapshots` создавать отдельные `sqlite3.connect(..., check_same_thread=False)` в каждом потоке-обработчике без глобального лока (WAL позволяет параллельное чтение).

---

### 2.4 Hot RAM-кэш поверх SQLite для топ-N ключей

**Где:** `CacheStore.get()` в `server/tinvest_server.py`  
**Что сейчас:** `_pcache` = dict[key → (hash, data)], LRU очищается при >500 ключей (`.clear()` — грубо!)  
**Ожидаемый эффект:** самые частые запросы (КБД, IMOEX, список ОФЗ, snapshot) — из RAM без SQLite  
**Как:**
```python
# Вместо self._pcache.clear() при >500 — LRU вытеснение:
from collections import OrderedDict
class LRUCache:
    def __init__(self, maxsize=512):
        self._d, self._n = OrderedDict(), maxsize
    def get(self, key): 
        if key in self._d: self._d.move_to_end(key); return self._d[key]
    def set(self, key, val):
        self._d[key] = val; self._d.move_to_end(key)
        if len(self._d) > self._n: self._d.popitem(last=False)
```
**Список ключей для принудительного прогрева при старте:** снэпшоты (`bonds`, `stocks`, `heatmap`), КБД, IMOEX, ключевая ставка ЦБ, BTC.

---

## 3. Среднее (M-размер, 2–4 часа)

### 3.1 Клиент: использовать `/v1/market/snapshot` при первом открытии экранов

**Где:** `src/py/13u_heatmap.py`, `src/py/13_ext_1_screener.py` → добавить хелпер из `src/py/12d_market_snap.py`  
**Что сейчас:** клиент при открытии тепловой карты или скринера делает 30–50 запросов к `/v1/proxy` (MOEX ISS по каждой бумаге серийно)  
**Ожидаемый эффект:** время первой загрузки скринера/карты 30–60+ с → 1–3 с (один compressed snapshot)  
**Как:**
1. `12d_market_snap.py`: `get_market_snapshot(kind)` — запрос `/v1/market/snapshot?kind=bonds` с локальным кэшем на 15 мин в SQLite
2. `screener_payload()` и `hm_bonds()` используют снэпшот как первичный источник, отдельные запросы — только для бумаг, которых нет в снэпшоте

---

### 3.2 nginx-прослойка (gzip + TLS offload + статика)

**Когда нужен:** >50 пользователей или появляется статический контент (логотипы, иконки, `favicon.ico`)  
**Что даёт:**
- TLS handshake переходит с Python на nginx → на 10–20 мс быстрее каждое соединение
- `gzip static` кэш — не пересжимает один и тот же JSON каждый раз
- `proxy_cache` — nginx сам кэширует ответы `/v1/market/snapshot` на 60–300 с без обращения к Python

```nginx
server {
    gzip on; gzip_types application/json text/plain;
    gzip_min_length 1400;
    gzip_comp_level 5;
    
    location /v1/market/snapshot {
        proxy_cache snap_cache;
        proxy_cache_valid 200 60s;
        proxy_pass http://127.0.0.1:8780;
    }
    location /v1/ {
        proxy_pass http://127.0.0.1:8780;
    }
}
```

---

### 3.3 Параллельная сборка снэпшота в `market_worker.py`

**Где:** `server/market_worker.py` — сейчас обход ISS идёт преимущественно последовательно  
**Как:** `concurrent.futures.ThreadPoolExecutor(max_workers=8)` для независимых запросов к MOEX ISS (разные `engine/market`), ЦБ и рейтинговых агентств при сборке снэпшота.  
**Ожидаемый эффект:** время полной пересборки снэпшота с 10–15 мин → 2–4 мин.

---

## 4. Крупное (L-размер, отдельная задача)

### 4.1 Incremental snapshot (дельта-обновление)

Вместо полной пересборки снэпшота каждые 15 мин — обновлять только то, что изменилось:
- В торговые часы: только котировки (`prices`, `chg_d`) — каждые 5 мин
- Ночью/выходные: только купоны, рейтинги, новые размещения — 1 раз в час
- Клиент запрашивает `?since=<timestamp>` и получает только дельту

### 4.2 Server-Sent Events (SSE) для live-котировок

При открытом окне программы — один `GET /v1/live/stream` держит постоянное HTTP/1.1-соединение, сервер пушит изменившиеся котировки раз в 3–5 сек в торговое время. Клиент не поллит 50 эндпоинтов каждые 30 сек.

### 4.3 Вынос фоновых воркеров в отдельные процессы

Сейчас `disclosure_worker`, `flows_worker`, `calc_worker`, `alerts` запускаются как потоки внутри `tinvest_server.py`. При тяжёлом HTML-парсинге (3116 выпусков в `13q_disclosure.py`) GIL блокирует HTTP.  
**Решение:** запускать каждый воркер как отдельный `systemd`-сервис через `subprocess.Popen` или выделить их в отдельные файлы с `multiprocessing`.

---

## 5. Метрики (добавить в `/v1/health`)

Сейчас в `/v1/health` нет данных о производительности. Добавить:
```json
{
  "cache_hit_rate": 0.94,
  "snapshot_age_sec": 312,
  "proxy_p50_ms": 18,
  "proxy_p95_ms": 142,
  "active_connections": 3,
  "pcache_size": 287
}
```
Уже есть `_stats` в `CacheStore` — собрать и отдать.

---

## 6. Приоритизация

| # | Задача | Эффект | Усилие | Когда |
|---|---|---|---|---|
| 1 | **gzip ответов** (п. 2.1) | 5–8× меньше трафика | S (2 ч) | Сейчас |
| 2 | **ETag/304** (п. 2.2) | 90% запросов ночью — 1–2 мс | S (3 ч) | Сейчас |
| 3 | **LRU вместо `.clear()`** (п. 2.4) | Нет provoked cache miss | S (1 ч) | Сейчас |
| 4 | **SQLite mmap + cache_size** (п. 2.3) | -20–40% latency чтения | S (30 мин) | Сейчас |
| 5 | **Клиент использует snapshot** (п. 3.1) | Скринер/карта 1–3 с вместо 60+ | M (4 ч) | Следующий спринт |
| 6 | **Параллельная сборка snapshot** (п. 3.3) | Пересборка 2–4 мин вместо 15 | M (3 ч) | Следующий спринт |
| 7 | **nginx** (п. 3.2) | TLS offload + статика | M (2 ч) | При >50 пользователях |
| 8 | **2 ядра + разделение процессов** (п. 4.3) | Нет GIL-конкуренции | L | При >100 пользователях |
| 9 | **Incremental snapshot** (п. 4.1) | Всегда свежие данные | L | v0.32 |
| 10 | **SSE live-котировки** (п. 4.2) | Real-time без поллинга | L | v0.33 |
