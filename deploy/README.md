# deploy/ — примеры для нагруженной раскладки

**Не развёрнуто, применять при >50–100 пользователях.**

Сейчас всё работает так, как описано в `server/README.md` и `server/deploy/` (один сервер данных, воркеры отдельными юнитами,
HTTP на 127.0.0.1:8780). Здесь лежат заготовки на случай роста нагрузки; см. `docs/PERFORMANCE_PLAN.md`, разделы 1, 3.2 и 4.3.

## Состав

| Файл | Назначение |
|---|---|
| `nginx/tanalytic.conf` | nginx: TLS-терминация, gzip, `proxy_cache` снэпшота рынка на 60 с, остальное — прозрачный прокси |
| `systemd/tanalytic-server.service` | HTTP-сервер данных (`tinvest_server.py`) |
| `systemd/tanalytic-market.service` | сборщик среза рынка отдельным процессом (`market_worker.py --loop`, до 4 параллельных запросов к MOEX) |
| `systemd/tanalytic-bot.service` | Telegram-бот (скрипта бота в этом репозитории нет, путь подставьте свой) |

Остальные воркеры (`flows_worker`, `disclosure_worker`, `calc_worker`) уже имеют готовые юниты в `server/deploy/`.
Проверка тревог (`alerts`) пока работает потоком внутри сервера данных (отключается переменной `TINVEST_ALERTS=0`).

## Порядок применения

1. Скопировать юниты в `/etc/systemd/system/`, поправить пути, пользователя и номера ядер в `CPUAffinity`, затем `systemctl daemon-reload`.
2. `systemctl enable --now tanalytic-market tanalytic-server`.
3. Положить `nginx/tanalytic.conf` в `/etc/nginx/conf.d/`, указать домен и сертификаты, `nginx -t && systemctl reload nginx`.
4. Сервер данных оставить на `127.0.0.1:8780`; наружу смотрит только nginx.

## Проверка

```
curl -sI -H 'Accept-Encoding: gzip' 'https://HOST/v1/market/snapshot?kind=bonds' | grep -i 'content-encoding\|etag\|x-cache'
curl -s http://127.0.0.1:8780/v1/health        # cache_hit_rate, latency_p50_ms / latency_p95_ms, snapshot_age_sec
```

## Замечания

- Сервер сам сжимает ответы по `Accept-Encoding: gzip` (тела больше 1 КБ) и выдаёт ETag / 304 для `/v1/market/snapshot`,
  `/v1/parsed/*` и GET `/v1/fetch`.
- Кэш nginx для снэпшота общий для всех клиентов и отдаётся до проверки ключа сервером. Если срез рынка нельзя показывать
  без ключа, добавьте `auth_request` на `/v1/auth/check` или уберите `proxy_cache` из `location /v1/market/snapshot`.
