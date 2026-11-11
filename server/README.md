# Сервер данных T-Invest Analytics

Небольшой HTTP-сервер (один файл `tinvest_server.py`, только стандартная библиотека Python 3.8+), который стоит между
приложением и публичными источниками данных и **кэширует** их ответы для всех пользователей.

## Зачем и как это устроено

```
приложение  ──►  сервер данных  ──►  MOEX ISS, ФНС ГИР БО, Банк России, smart-lab, рейтинговые агентства
(на компьютере)   (кэш + лимиты)      (публичные страницы и API)
```

Без сервера каждый пользователь сам делает сотни запросов к Мосбирже и ФНС. С сервером запрос идёт один раз, ответ
сохраняется в общем кэше и отдаётся всем, а нагрузка на источник ограничивается (Мосбиржа ~8 запросов/с, ФНС 2/с, smart-lab 1/с, остальные 2/с).

Что делает сервер:

- `GET /v1/health` — `{ok, version, uptime, cache_items}`;
- `GET /v1/stats` — счётчики по хостам, доля попаданий в кэш, ошибки источников (без адресов клиентов);
- `GET|POST /v1/fetch?url=<url-кодированный адрес>` — получить страницу источника. Ответ: статус источника, тело (в том числе
  бинарное, например PDF Банка России), `Content-Type`, заголовки `X-Cache: hit|miss|stale` и `X-Age`.

Правила:

- Разрешены только публичные хосты из списка в коде (`ALLOWED_HOSTS`): `iss.moex.com`, `www.moex.com`, `bo.nalog.gov.ru`, `www.cbr.ru`, `cbr.ru`,
  `smart-lab.ru`, `raexpert.ru`, `ratings.ru`, `investmint.ru`, `invest-brands.cdn-tinkoff.ru`, `t.me/s/…` (зеркало канала с рейтингами).
  Всё остальное получает 403, как и редиректы на посторонние хосты. API Т-Инвестиций и Telegram Bot API в списке нет.
- Время жизни кэша задаётся таблицей `RULES` в коде: котировки и списки Мосбиржи — 5 минут в торговые часы (иначе час), история и описания — 1–3 суток,
  эмитенты — 7 суток, кривая КБД — час, ФНС — 7 суток, smart-lab — 5 суток, Банк России — 6–12 часов, рейтинги — 12 часов, логотипы — 30 суток, прочее — час.
- Если источник недоступен, отдаётся устаревшая копия (`X-Cache: stale`). Ответы 5xx не кэшируются, 404 кэшируется на 10 минут.
- Одинаковые одновременные запросы объединяются в один запрос к источнику.
- POST кэшируется только по явному правилу (сейчас — поиск эмитента на raexpert.ru); ключ кэша — адрес и хэш тела.
- Размер кэша ограничен (`--max-mb`, по умолчанию 1024); при переполнении удаляются записи, к которым дольше всего не обращались.

Клиент при любой проблеме сервера (нет связи, таймаут, 5xx, неверный ключ) молча ходит к источникам напрямую и на 5 минут перестаёт обращаться к серверу.

## Что видит сервер, что хранит

- **Видит:** адреса публичных страниц, которые запрашивает приложение. В них бывают ISIN, тикеры и ИНН бумаг и эмитентов, которые
  пользователь открывает. IP-адреса клиентов в статистике не хранятся.
- **Не видит:** токен Т-Инвестиций, счета, позиции, операции. Они идут напрямую в Т-Банк и на сервер не попадают.
- **Хранит:** только кэш публичных ответов в SQLite: `cache.sqlite` (режим WAL) в каталоге `--data`. Пользовательских данных нет.
- **Журнал:** по умолчанию адреса запросов не пишутся. Флаг `--verbose` включает строки вида `GET /v1/fetch?url=…` (для отладки).
- Если запускаете сервер для других людей, скажите им, что запрошенные адреса источников проходят через ваш сервер.

## Запуск локально

```
python3 server/tinvest_server.py                       # 127.0.0.1:8780, кэш в ~/.tinvest_server
python3 server/tinvest_server.py --port 8780 --data ./srvdata --key МОЙ_КЛЮЧ
python3 server/tinvest_server.py --version
```

Флаги: `--host`, `--port`, `--data`, `--key` (или переменная `TINVEST_SERVER_KEY`), `--max-mb`, `--verbose`.
Если задан ключ, каждый запрос обязан содержать заголовок `X-Client-Key` (сравнение за постоянное время); без ключа сервер открыт для всех, кто до него дотянется,
поэтому на публичном адресе ключ нужен.

Подключение приложения: «Настройки → Сервер данных» (адрес, например `http://127.0.0.1:8780`, и ключ, кнопка «Проверить») либо
переменные окружения `TINVEST_DATA_SERVER` и `TINVEST_DATA_KEY` перед запуском приложения.

## Развёртывание на VPS

1. Создайте отдельного пользователя и каталоги:

   ```
   sudo useradd --system --home /var/lib/tinvest-server --shell /usr/sbin/nologin tinvest
   sudo mkdir -p /opt/tinvest-server /var/lib/tinvest-server
   sudo cp tinvest_server.py /opt/tinvest-server/
   sudo chown -R tinvest:tinvest /var/lib/tinvest-server
   ```

2. Ключ доступа положите в файл окружения (права 0600), чтобы он не светился в списке процессов:

   ```
   echo 'TINVEST_SERVER_KEY=сгенерируйте_длинную_случайную_строку' | sudo tee /etc/tinvest-server.env
   sudo chmod 600 /etc/tinvest-server.env
   ```

3. Юнит systemd `/etc/systemd/system/tinvest-server.service`:

   ```
   [Unit]
   Description=T-Invest Analytics data server
   After=network-online.target
   Wants=network-online.target

   [Service]
   User=tinvest
   Group=tinvest
   EnvironmentFile=/etc/tinvest-server.env
   ExecStart=/usr/bin/python3 /opt/tinvest-server/tinvest_server.py --host 127.0.0.1 --port 8780 --data /var/lib/tinvest-server
   Restart=on-failure
   NoNewPrivileges=true
   ProtectSystem=strict
   ProtectHome=true
   PrivateTmp=true
   ReadWritePaths=/var/lib/tinvest-server

   [Install]
   WantedBy=multi-user.target
   ```

   ```
   sudo systemctl daemon-reload
   sudo systemctl enable --now tinvest-server
   curl -H "X-Client-Key: ..." http://127.0.0.1:8780/v1/health
   ```

## Cloudflare Tunnel

Сервер слушает только `127.0.0.1`, наружу его выставляет именованный туннель `cloudflared`: открывать порты на VPS не нужно.

```
cloudflared tunnel login
cloudflared tunnel create tinvest-data
cloudflared tunnel route dns tinvest-data data.example.ru
```

`/etc/cloudflared/config.yml`:

```
tunnel: tinvest-data
credentials-file: /etc/cloudflared/<ID-туннеля>.json
ingress:
  - hostname: data.example.ru
    service: http://127.0.0.1:8780
  - service: http_status:404
```

```
sudo cloudflared service install
```

Cloudflare терминирует TLS: между пользователем и Cloudflare трафик шифруется, а Cloudflare технически видит запросы (адреса публичных страниц и ключ
в заголовке). Внутри VPS трафик идёт по `127.0.0.1`. В приложении укажите `https://data.example.ru` и ключ.

## Обновление

```
sudo cp tinvest_server.py /opt/tinvest-server/tinvest_server.py
sudo systemctl restart tinvest-server
```

Кэш в `/var/lib/tinvest-server` сохраняется. Чтобы сбросить его целиком, остановите сервис и удалите `cache.sqlite*`.

## На будущее

Проверка доступа вынесена в функцию `authorize()` в `tinvest_server.py` — сюда подключится вход через Telegram (сессия пользователя вместо общего ключа).
