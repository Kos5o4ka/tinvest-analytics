#!/bin/bash
# Подпись и нотаризация macOS. Без секретов Apple ничего не ломает: приложение подписывается ad-hoc, нотаризация пропускается.
#   packaging/mac_codesign.sh setup            импорт сертификата Developer ID во временную связку ключей (если задан APPLE_DEVELOPER_ID_CERT)
#   packaging/mac_codesign.sh app <.app>       подпись приложения (Developer ID + hardened runtime + entitlements, иначе ad-hoc)
#   packaging/mac_codesign.sh dir <папка>      подпись всех Mach-O в папке (Python-сервер для ресурсов Tauri): Developer ID + hardened runtime, иначе ad-hoc
#   packaging/mac_codesign.sh dmg <.dmg>       подпись образа (только Developer ID)
#   packaging/mac_codesign.sh notarize <файл>  нотаризация и staple (только если заданы APPLE_ID, APPLE_TEAM_ID, APPLE_APP_PASSWORD)
#   packaging/mac_codesign.sh cleanup          удалить временную связку ключей
# Секреты (переменные окружения, в CI — secrets репозитория):
#   APPLE_DEVELOPER_ID_CERT (.p12 в base64), APPLE_CERT_PASSWORD, APPLE_ID, APPLE_TEAM_ID, APPLE_APP_PASSWORD (пароль для приложений).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
KC_PATH="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/tanalytic-build.keychain-db"
IDENT_FILE="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/tanalytic-identity.txt"

identity() { [ -s "$IDENT_FILE" ] && cat "$IDENT_FILE" || true; }
have_notary() { [ -n "${APPLE_ID:-}" ] && [ -n "${APPLE_TEAM_ID:-}" ] && [ -n "${APPLE_APP_PASSWORD:-}" ]; }

setup() {
  rm -f "$IDENT_FILE"
  if [ -z "${APPLE_DEVELOPER_ID_CERT:-}" ] || [ -z "${APPLE_CERT_PASSWORD:-}" ]; then
    echo "Сертификат Developer ID не задан: приложение будет подписано ad-hoc (без нотаризации)."; return 0
  fi
  local p12 pw; p12="$(mktemp -t tanalytic-cert).p12"; pw="$(uuidgen)"
  echo "$APPLE_DEVELOPER_ID_CERT" | base64 --decode > "$p12"
  security create-keychain -p "$pw" "$KC_PATH"
  security set-keychain-settings -lut 21600 "$KC_PATH"
  security unlock-keychain -p "$pw" "$KC_PATH"
  security import "$p12" -k "$KC_PATH" -P "$APPLE_CERT_PASSWORD" -T /usr/bin/codesign -T /usr/bin/security
  rm -f "$p12"
  security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$pw" "$KC_PATH" >/dev/null
  security list-keychains -d user -s "$KC_PATH" $(security list-keychains -d user | tr -d '"')
  local id; id="$(security find-identity -v -p codesigning "$KC_PATH" | grep "Developer ID Application" | head -1 | sed -E 's/^[^"]*"([^"]+)".*/\1/')"
  if [ -z "$id" ]; then echo "::warning::в сертификате нет Developer ID Application: подписываю ad-hoc" >&2; return 0; fi
  echo "$id" > "$IDENT_FILE"
  echo "Подпись: $id"
}

sign_app() {
  local app="$1" id; id="$(identity)"
  if [ -z "$id" ]; then
    # arm64-бинарники без подписи macOS не запускает («повреждён»): подписываем ad-hoc явно
    codesign --force --deep -s - "$app"
  else
    # Сначала все вложенные исполняемые файлы и библиотеки (самые глубокие первыми), затем сам пакет.
    # --deep у пакета не нужен и Apple его не рекомендует: всё вложенное уже подписано с теми же параметрами.
    find "$app/Contents" -type f -print0 | while IFS= read -r -d '' f; do
      if file -b "$f" | grep -q "Mach-O"; then echo "$f"; fi
    done | awk '{ print length($0) "\t" $0 }' | sort -rn | cut -f2- | while IFS= read -r f; do
      codesign --force --timestamp --options runtime --entitlements "$HERE/entitlements.plist" -s "$id" "$f"
    done
    codesign --force --timestamp --options runtime --entitlements "$HERE/entitlements.plist" -s "$id" "$app"
  fi
  codesign --verify --deep --strict "$app"
  codesign -dv "$app" 2>&1 | head -6
}

sign_dir() {
  local dir="$1" id; id="$(identity)"
  # самые глубокие файлы первыми; каждому Mach-O своя подпись (в папке PyInstaller их сотни: .so, .dylib, исполняемый файл)
  find "$dir" -type f -print0 | while IFS= read -r -d '' f; do
    if file -b "$f" | grep -q "Mach-O"; then echo "$f"; fi
  done | awk '{ print length($0) "\t" $0 }' | sort -rn | cut -f2- | while IFS= read -r f; do
    if [ -z "$id" ]; then
      codesign --force -s - "$f"
    else
      codesign --force --timestamp --options runtime --entitlements "$HERE/entitlements.plist" -s "$id" "$f"
    fi
  done
  echo "Подписано: $dir"
}

sign_dmg() {
  local id; id="$(identity)"
  if [ -z "$id" ]; then echo "Образ без подписи (нет Developer ID)."; return 0; fi
  codesign --force --timestamp -s "$id" "$1"
  codesign --verify --strict "$1"
}

notarize() {
  if [ -z "$(identity)" ] || ! have_notary; then echo "Нотаризация пропущена: нет Developer ID или APPLE_ID/APPLE_TEAM_ID/APPLE_APP_PASSWORD."; return 0; fi
  local out; out="$(xcrun notarytool submit "$1" --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" --password "$APPLE_APP_PASSWORD" --wait --output-format json)" || { echo "$out"; echo "::error::нотаризация не удалась" >&2; exit 1; }
  echo "$out"
  echo "$out" | grep -q '"status" *: *"Accepted"' || { echo "::error::Apple отклонила нотаризацию (журнал: xcrun notarytool log <id>)" >&2; exit 1; }
  xcrun stapler staple "$1"
  xcrun stapler validate "$1"
}

cleanup() { security delete-keychain "$KC_PATH" 2>/dev/null || true; rm -f "$IDENT_FILE"; }

case "${1:-}" in
  setup) setup ;;
  app) sign_app "${2:?нужен путь к .app}" ;;
  dir) sign_dir "${2:?нужна папка}" ;;
  dmg) sign_dmg "${2:?нужен путь к .dmg}" ;;
  notarize) notarize "${2:?нужен путь к файлу}" ;;
  cleanup) cleanup ;;
  *) sed -n '2,10p' "$0"; exit 2 ;;
esac
