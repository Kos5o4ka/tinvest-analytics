#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T-Invest Analytics — аналитика брокерских счетов Т-Инвестиций и отчётов других брокеров.

Один файл, только стандартная библиотека Python 3.8+. Запуск:

    python tinvest_analytics.py              # откроется окно приложения
    python tinvest_analytics.py --no-window  # только сервер: http://127.0.0.1:8765

Все данные хранятся локально в ~/.tinvest_analytics (база SQLite data.db, логотипы, настройки).
Токен никуда, кроме API Т-Банка, не отправляется.
"""
import base64
import bisect
import csv
import gzip
import hashlib
import io
import json
import os
import platform
import re
import shutil
import sqlite3
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
import zipfile
import zlib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse
from xml.etree import ElementTree as ET

APP_NAME = "T-Invest Analytics"
APP_VERSION = "0.11"
APP_DIR = os.environ.get("TINVEST_HOME") or os.path.join(os.path.expanduser("~"), ".tinvest_analytics")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
DB_PATH = os.path.join(APP_DIR, "data.db")
LOGO_DIR = os.path.join(APP_DIR, "logos")
CONTRACT = "tinkoff.public.invest.api.contract.v1"
LOGO_CDN = "https://invest-brands.cdn-tinkoff.ru/"
D0 = Decimal(0)
DAY = 86400

# Реестр дополнительных маршрутов: модули регистрируют обработчики, сервер вызывает их.
#   API_GET["/api/x"] = fn(cfg, acc, q, force)  -> dict (JSON) или кортеж (код, тело, content-type, заголовки)
#   API_POST["/api/x"] = fn(cfg, body)           -> dict (JSON) или такой же кортеж
API_GET, API_POST = {}, {}
# Функции без аргументов, которые сервер вызывает один раз при запуске (фоновые потоки модулей).
STARTUP_HOOKS = []
# Ключи настроек, которые никогда не отдаются в интерфейс через /api/config (секреты).
SECRET_KEYS = {"token"}

DEFAULT_CONFIG = {
    "token": "",
    "sandbox": True,
    "hosts_prod": ["https://invest-public-api.tbank.ru/rest", "https://invest-public-api.tinkoff.ru/rest"],
    "hosts_sandbox": ["https://sandbox-invest-public-api.tbank.ru/rest",
                      "https://sandbox-invest-public-api.tinkoff.ru/rest"],
    "verify_ssl": True,
    "ca_file": "",
    "port": 8765,
    "theme": "auto",        # auto | dark | light
    "targets": {},          # целевые доли по классам активов, %: {"share": 50, "bond": 40, ...}
    "notify_days": 7,       # за сколько дней напоминать о выплатах
    "keyrate_mode": "cbr",  # источник прогноза ключевой ставки для флоатеров: cbr | survey | market | flat
    "mon_drop5": 3.0, "mon_drop30": 7.0, "mon_spread30": 2.0, "mon_sell_days": 5.0, "mon_offer_days": 30,   # пороги тревог «Мониторинга»
}

