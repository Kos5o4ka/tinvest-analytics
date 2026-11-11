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

- `GET /v1/health` — открыт без ключа: `{ok, version, uptime, cache_items, auth: "keys"|"key"|"none", bot}`;
- `GET /v1/auth/check` — проверка ключа из `X-Client-Key`: 200 `{ok, expires, username, plan, bot}` или 401 `{ok:false, error:"invalid"|"expired"|"banned", bot}`;
- `POST /v1/notify` — поставить в очередь Telegram-уведомление пользователю (см. «Уведомления через бота» ниже);
- `GET /v1/stats` — счётчики по хостам, доля попаданий в кэш, ошибки источников (без адресов клиентов);
- `GET|POST /v1/fetch?url=<url-кодированный адрес>` — получить страницу источника. Ответ: статус источника, тело (в том числе
  бинарное, например PDF Банка России), `Content-Type`, заголовки `X-Cache: hit|miss|stale` и `X-Age`.

Правила:

- Разрешены только публичные хосты из списка в коде (`ALLOWED_HOSTS`): `iss.moex.com`, `www.moex.com`, `bo.nalog.gov.ru`, `www.cbr.ru`, `cbr.ru`,
  `smart-lab.ru`, `raexpert.ru`, `ratings.ru`, `investmint.ru`, `invest-brands.cdn-tinkoff.ru`, `t.me/s/…` (зеркало канала с рейтингами).
  Всё остальное получает 403, как и редиректы на посторонние хосты. API Т-Инвестиций и Telegram Bot API в списке нет (уведомления идут не через `/v1/fetch`, а через `/v1/notify` и бота).
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
  Исключение — тексты уведомлений, которые пользователь сам включил в приложении (названия бумаг и суммы в тревогах и сводке): они проходят через сервер и бот.
- **Хранит:** кэш публичных ответов в SQLite: `cache.sqlite` (режим WAL) в каталоге `--data`. Текст уведомлений лежит в очереди `outbox` общей базы бота только до отправки
  и удаляется сразу после доставки; в журнал текст не пишется. Для лимитов хранятся лишь пары «Telegram ID, время» (`notify_log`, записи старше суток удаляются).
- **Журнал:** по умолчанию адреса запросов не пишутся. Флаг `--verbose` включает строки вида `GET /v1/fetch?url=…` (для отладки).
- Если запускаете сервер для других людей, скажите им, что запрошенные адреса источников проходят через ваш сервер.

## Запуск локально

```
python3 server/tinvest_server.py                       # 127.0.0.1:8780, кэш в ~/.tinvest_server
python3 server/tinvest_server.py --port 8780 --data ./srvdata --key МОЙ_КЛЮЧ
python3 server/tinvest_server.py --version
```

Флаги: `--host`, `--port`, `--data`, `--key` (или переменная `TINVEST_SERVER_KEY`), `--keys-db` (`TINVEST_KEYS_DB`), `--bot` (`TINVEST_BOT`), `--max-mb`, `--verbose`.
Если задан ключ, каждый запрос обязан содержать заголовок `X-Client-Key` (сравнение за постоянное время); без ключа сервер открыт для всех, кто до него дотянется,
поэтому на публичном адресе ключ нужен.

Подключение приложения: «Настройки → Сервер данных» (адрес, например `http://127.0.0.1:8780`, и ключ, кнопка «Проверить») либо
переменные окружения `TINVEST_DATA_SERVER` и `TINVEST_DATA_KEY` перед запуском приложения.

## Развёртывание на VPS

Сервер данных и Telegram-бот работают на одном VPS от одного пользователя `tinvest` и делят базу ключей
`/var/lib/tinvest-bot/keys.sqlite`. Код ставится git-клонами, каждую ночь в 03:00 МСК таймер подтягивает обновления
и перезапускает только то, что изменилось. Готовые файлы лежат в `server/deploy/`.

1. Пользователь и каталоги:

   ```
   sudo useradd --system --home /var/lib/tinvest-server --shell /usr/sbin/nologin tinvest
   sudo mkdir -p /var/lib/tinvest-server /var/lib/tinvest-bot
   sudo chown tinvest:tinvest /var/lib/tinvest-server /var/lib/tinvest-bot
   ```

2. Код сервера (публичный репозиторий):

   ```
   sudo git clone https://github.com/Kos5o4ka/tinvest-analytics.git /opt/tinvest-analytics
   ```

3. Код бота (закрытый репозиторий) через deploy-ключ только на чтение:

   ```
   sudo ssh-keygen -t ed25519 -N "" -f /root/.ssh/tinvest_bot_deploy
   sudo cat /root/.ssh/tinvest_bot_deploy.pub
   ```

   Добавьте ключ в GitHub: репозиторий tinvest-bot → Settings → Deploy keys → Add deploy key (галочку «Allow write access» не ставьте). Затем:

   ```
   sudo GIT_SSH_COMMAND="ssh -i /root/.ssh/tinvest_bot_deploy -o IdentitiesOnly=yes" \
        git clone git@github.com:Kos5o4ka/tinvest-bot.git /opt/tinvest-bot
   sudo git -C /opt/tinvest-bot config core.sshCommand "ssh -i /root/.ssh/tinvest_bot_deploy -o IdentitiesOnly=yes"
   ```

4. Настройки бота: `sudo cp /opt/tinvest-bot/.env.example /etc/tinvest-bot.env && sudo chmod 600 /etc/tinvest-bot.env`, впишите `BOT_TOKEN`
   от @BotFather и свой Telegram ID в `ADMIN_ID`, `KEYS_DB=/var/lib/tinvest-bot/keys.sqlite`.
   По желанию общий ключ для своих клиентов и мониторинга: `echo 'TINVEST_SERVER_KEY=длинная_случайная_строка' | sudo tee /etc/tinvest-server.env`.

5. Сервисы и таймер:

   ```
   sudo cp /opt/tinvest-bot/tinvest-bot.service /etc/systemd/system/
   sudo cp /opt/tinvest-analytics/server/deploy/tinvest-server.service \
           /opt/tinvest-analytics/server/deploy/tinvest-update.service \
           /opt/tinvest-analytics/server/deploy/tinvest-update.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now tinvest-bot          # первым: создаёт базу ключей
   sudo systemctl enable --now tinvest-server
   sudo systemctl enable --now tinvest-update.timer
   ```

6. Проверка:

   ```
   curl http://127.0.0.1:8780/v1/health                 # "auth": "keys", "bot": "tanalyticbot"
   systemctl list-timers tinvest-update.timer           # когда следующий запуск
   journalctl -u tinvest-bot -u tinvest-server -n 50    # журналы
   ```

   Напишите боту `/start`, получите ключ и проверьте: `curl -H "X-Client-Key: TIA-…" http://127.0.0.1:8780/v1/auth/check`.

Если сервер уже работал по старой схеме (`/opt/tinvest-server/tinvest_server.py`), остановите и отключите старый юнит перед шагом 5,
кэш в `/var/lib/tinvest-server` подхватится новым сервисом.

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

Автоматически: `tinvest-update.timer` в 03:00 МСК запускает `server/deploy/tinvest-update.sh`. Скрипт делает `git fetch` обоих
репозиториев, при новых коммитах в `main` переключает код, проверяет, что Python-файл компилируется, перезапускает сервис и через 5 секунд
проверяет, что он жив (для сервера данных ещё и `/v1/health`). Если сервис не поднялся, код откатывается на прежний коммит.
Без изменений ничего не перезапускается: ежедневный перезапуск «на всякий случай» не нужен, упавший сервис systemd поднимает сам (`Restart=always`).

Вручную, не дожидаясь ночи: `sudo systemctl start tinvest-update && journalctl -u tinvest-update -n 20`.

Если поменялись сами юниты в `server/deploy/`, скопируйте их заново в `/etc/systemd/system/` и выполните `sudo systemctl daemon-reload`.
Кэш в `/var/lib/tinvest-server` сохраняется. Чтобы сбросить его целиком, остановите сервис и удалите `cache.sqlite*`.

## Вход по ключу из Telegram-бота

Доступ к приложению выдаёт бот `@tanalyticbot` (по умолчанию; меняется флагом `--bot`): он присылает ключ вида `TIA-XXXX-XXXX-XXXX`, действующий 24 часа.
Бот живёт в **отдельном закрытом репозитории** и пишет в SQLite-файл, который этот сервер только читает (файл общий, режим WAL):

```
python3 tinvest_server.py --keys-db /var/lib/tinvest-bot/keys.sqlite --bot tanalyticbot
```

Контракт базы (создаёт и ведёт бот):

```
users(tg_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, created REAL, consent REAL,
      banned INTEGER NOT NULL DEFAULT 0, plan TEXT NOT NULL DEFAULT 'free')
keys(key_hash TEXT PRIMARY KEY, tg_id INTEGER NOT NULL, created REAL NOT NULL, expires REAL NOT NULL,
     revoked INTEGER NOT NULL DEFAULT 0, last_used REAL)
```

`key_hash = sha256(normalize(key))` в hex, `normalize(k) = k.strip().upper().replace(" ", "")`; время — unix-секунды. Сами ключи в базе не хранятся.

Ключ принимается, если запись есть, `revoked = 0`, `expires` в будущем и пользователь не забанен. Клиент получает идентификатор `tg:<tg_id>`.
Отказ приходит как 401 с `error`: `invalid` (неизвестный ключ), `expired` (истёк или отозван), `banned`.

- Проверки кэшируются в памяти: успешные на 60 секунд, но не дольше `expires`; отказы на 10 секунд. Отзыв ключа и бан действуют с задержкой до минуты.
- Сервер сам пишет в базу только `keys.last_used` (не чаще раза в минуту на ключ, ошибки блокировки игнорируются). База открывается отдельным соединением на поток, с `busy_timeout`.
- Если базу не удалось открыть, запросы с ключами получают 401, в журнал один раз пишется причина; сервер не падает.
- Общий `--key` продолжает работать наряду с ключами бота (подходит для своих клиентов и мониторинга). Если не задано ни то ни другое, доступ открыт.
- В приложении по умолчанию используется `https://aurora-bot.duckdns.org:8443/tinvest`; токен Т-Инвестиций на сервер и в бот не передаётся.

## Уведомления через бота

Приложение больше не требует личного бота (токен и chat id): уведомления (тревоги мониторинга, наблюдение и цели, ближайшие выплаты, ежедневная сводка,
тестовое сообщение) отправляет тот же бот, что выдаёт ключ. Telegram ID пользователя известен по ключу.

`POST /v1/notify` с заголовком `X-Client-Key` (только ключ из бота) и телом `{"text": "<b>HTML</b> Telegram"}`:

| Ответ | Когда |
|---|---|
| 200 `{"ok":true,"queued":<id>}` | сообщение поставлено в очередь |
| 400 `{"error":"empty_text"}` / `{"error":"text_too_long","max":3500}` | пустой текст или длиннее 3500 символов |
| 401 | ключ не принят (`invalid`/`expired`/`banned`) |
| 403 `{"error":"уведомления доступны только по ключу из бота"}` | общий `--key` или открытый сервер: адресата нет |
| 409 `{"ok":false,"error":"notify_off"}` | пользователь выключил уведомления в боте (`/notify_off`) |
| 429 `{"ok":false,"error":"rate_limit"}` | больше 30 сообщений в час или 200 в сутки на пользователя |

Сервер вставляет строку в таблицу `outbox` общей базы (создаёт её `IF NOT EXISTS`, если бот ещё не обновлён) и записывает отметку в `notify_log`; лимиты считаются
по ней, поэтому переживают перезапуск. Дальше сообщение забирает бот (поток-отправитель раз в ~2 секунды), отправляет с `parse_mode=HTML`
и удаляет строку. Схема версии 2 (ведёт бот): `outbox(id, tg_id, text, created, tries)`, `notify_log(tg_id, created)`, `users.notify INTEGER NOT NULL DEFAULT 1`.

Конфиденциальность: текст проходит через сервер данных и бот и после доставки нигде не хранится; в журналы (в том числе при `--verbose`) он не попадает.
Сообщения, которые не удалось доставить за час, удаляются. Уведомления приходят, только пока приложение запущено.

## На будущее

Проверка доступа вынесена в функцию `authorize_ex()` / `authorize()` в `tinvest_server.py`.
