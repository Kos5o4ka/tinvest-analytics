#!/bin/bash
# Образ диска macOS: TAnalytic.app и ярлык на «Программы». Только hdiutil и osascript из системы.
#   packaging/make_dmg.sh <TAnalytic.app> <выход.dmg> [имя тома]
# Раскладка окна (иконки, фон) задаётся через Finder (AppleScript). Если он недоступен или завис (нет сеанса, нет прав
# на автоматизацию, DMG_NO_LAYOUT=1), образ собирается без раскладки: он так же рабочий, окно просто стандартное.
set -euo pipefail
APP="${1:?нужен путь к TAnalytic.app}"; OUT="${2:?нужен путь результата .dmg}"; VOL="${3:-TAnalytic}"
HERE="$(cd "$(dirname "$0")" && pwd)"
test -d "$APP/Contents/MacOS" || { echo "нет приложения: $APP" >&2; exit 1; }
WORK="$(mktemp -d "${TMPDIR:-/tmp}/tanalytic-dmg.XXXXXX")"
MNT=""
cleanup() {
  if [ -n "$MNT" ] && [ -d "$MNT" ]; then hdiutil detach "$MNT" -quiet 2>/dev/null || hdiutil detach "$MNT" -force -quiet 2>/dev/null || true; fi
  rm -rf "$WORK"
}
trap cleanup EXIT

STAGE="$WORK/stage"; mkdir -p "$STAGE/.background"
ditto "$APP" "$STAGE/TAnalytic.app"
ln -s /Applications "$STAGE/Applications"
HAVE_BG=0
if [ "${DMG_NO_LAYOUT:-0}" != "1" ] && python3 "$HERE/make_dmg_bg.py" "$STAGE/.background/bg.png" 2>/dev/null; then HAVE_BG=1; fi

SIZE_MB=$(( $(du -sm "$STAGE" | cut -f1) * 12 / 10 + 20 ))
RW="$WORK/rw.dmg"
hdiutil create -quiet -volname "$VOL" -srcfolder "$STAGE" -fs HFS+ -format UDRW -size "${SIZE_MB}m" -ov "$RW"

if [ "${DMG_NO_LAYOUT:-0}" != "1" ]; then
  # Finder видит том только без -nobrowse
  MNT="$(hdiutil attach -noverify -noautoopen -readwrite "$RW" | grep -o '/Volumes/.*$' | tail -1)"
  BGLINE=""; [ "$HAVE_BG" = 1 ] && BGLINE='set background picture of viewOptions to file ".background:bg.png"'
  cat > "$WORK/layout.applescript" <<OSA
tell application "Finder"
  tell disk "$VOL"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set the bounds of container window to {200, 120, 760, 480}
    set viewOptions to the icon view options of container window
    set arrangement of viewOptions to not arranged
    set icon size of viewOptions to 96
    set text size of viewOptions to 13
    $BGLINE
    set position of item "TAnalytic.app" of container window to {150, 170}
    set position of item "Applications" of container window to {410, 170}
    close
    open
    update without registering applications
    delay 2
    close
  end tell
end tell
OSA
  osascript "$WORK/layout.applescript" >/dev/null 2>&1 &
  OPID=$!
  for _ in $(seq 1 60); do kill -0 "$OPID" 2>/dev/null || break; sleep 1; done
  if kill -0 "$OPID" 2>/dev/null; then kill "$OPID" 2>/dev/null || true; echo "предупреждение: Finder не ответил за 60 с, образ без раскладки" >&2
  elif ! wait "$OPID"; then echo "предупреждение: раскладка окна не удалась, образ без раскладки" >&2
  fi
  sync
  for _ in 1 2 3 4 5; do hdiutil detach "$MNT" -quiet 2>/dev/null && break || sleep 2; done
  hdiutil detach "$MNT" -force -quiet 2>/dev/null || true
  MNT=""
fi

rm -f "$OUT"
hdiutil convert "$RW" -quiet -format UDZO -imagekey zlib-level=9 -o "$OUT"
hdiutil verify -quiet "$OUT"
echo "образ: $OUT ($(du -h "$OUT" | cut -f1))"
