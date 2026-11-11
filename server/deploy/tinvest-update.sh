#!/bin/sh
# Ежесуточное обновление сервера данных и Telegram-бота из GitHub (запускает tinvest-update.timer).
# Перезапускает сервис только если в ветке main появились новые коммиты. После перезапуска проверяет,
# что сервис жив; если нет — откатывает код на прежний коммит и перезапускает снова.
set -u

DATA_DIR=${DATA_DIR:-/opt/tinvest-analytics}     # клон публичного репозитория tinvest-analytics
BOT_DIR=${BOT_DIR:-/opt/tinvest-bot}             # клон закрытого репозитория tinvest-bot
HEALTH=${HEALTH:-http://127.0.0.1:8780/v1/health}

healthy() {   # $1 — имя сервиса
    sleep 5
    systemctl is-active --quiet "$1" || return 1
    if [ "$1" = tinvest-server ]; then
        python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('$HEALTH', timeout=10).status == 200 else 1)" \
            2>/dev/null || return 1
    fi
    return 0
}

update() {    # $1 — каталог, $2 — сервис, $3 — файл, который должен компилироваться
    dir=$1 svc=$2 main=$3
    if [ ! -d "$dir/.git" ]; then echo "$svc: $dir не git-клон, пропуск"; return 0; fi
    old=$(git -C "$dir" rev-parse HEAD)
    if ! git -C "$dir" fetch -q origin main; then echo "$svc: не удалось скачать обновления"; return 1; fi
    new=$(git -C "$dir" rev-parse origin/main)
    if [ "$old" = "$new" ]; then echo "$svc: без изменений ($(echo "$old" | cut -c1-7))"; return 0; fi
    git -C "$dir" reset -q --hard "$new"
    if ! python3 -m py_compile "$dir/$main"; then
        echo "$svc: $main не компилируется, откат"; git -C "$dir" reset -q --hard "$old"; return 1
    fi
    systemctl restart "$svc"
    if healthy "$svc"; then
        echo "$svc: обновлён $(echo "$old" | cut -c1-7) -> $(echo "$new" | cut -c1-7)"
        return 0
    fi
    echo "$svc: после обновления не поднялся, откат на $(echo "$old" | cut -c1-7)"
    git -C "$dir" reset -q --hard "$old"
    systemctl restart "$svc"
    return 1
}

rc=0
update "$BOT_DIR" tinvest-bot bot.py || rc=1                                  # сначала бот: он ведёт базу ключей
update "$DATA_DIR" tinvest-server server/tinvest_server.py || rc=1
exit $rc
