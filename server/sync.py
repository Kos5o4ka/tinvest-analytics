"""Облачная копия данных пользователя и вход в один клик (auth_<нонс>). Только стандартная библиотека.

Облачная копия (user_sync): ОДИН зашифрованный на компьютере пользователя блок. Ключ шифрования выводится из кодовой
фразы, которую знает только пользователь; сервер её не получает и содержимое прочитать не может: он хранит шифртекст,
номер версии (rev), соль для вывода ключа и контрольную сумму шифртекста. Слияние версий делает приложение
(сервер при конфликте лишь отдаёт актуальный блок). Токен Т-Инвестиций в блок не входит.

Очередь операций из бота (user_sync_queue) лежит открытым текстом, потому что пользователь сам отправил эти данные боту:
запись хранится, пока приложение не заберёт её и не подтвердит (ack_queue_ids) в той же транзакции, что и новая версия блока.

Вход в один клик (auth_links): pending -> approved -> consumed, срок жизни AUTH_TTL секунд. Нонс из ссылки
t.me/<бот>?start=auth_<нонс> в базе хранится только хешем; приложение доказывает, что это оно, секретом verifier
(в базе его хеш). Ключ доступа бот кладёт в строку на время до выдачи приложению и сразу стирает.
"""
import base64
import binascii
import hashlib
import hmac
import json
import re
import sqlite3
import threading
import time
from urllib.parse import quote

MAX_BLOB = 4 * 1024 * 1024            # размер шифртекста на пользователя
MAX_BODY = 6 * 1024 * 1024            # тело запроса push (base64 + JSON)
QUEUE_MAX = 200                       # операций из бота, ожидающих приложение
QUEUE_TTL = 60 * 86400
PUSH_PER_HOUR = 120
SALT_RX = re.compile(r"^[A-Za-z0-9+/=_-]{16,64}$")
SHA_RX = re.compile(r"^[0-9a-f]{64}$")

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS user_sync(tg_id INTEGER PRIMARY KEY, rev INTEGER NOT NULL DEFAULT 1, sha256 TEXT NOT NULL, "
    "updated_at REAL NOT NULL, device TEXT NOT NULL DEFAULT '', salt TEXT NOT NULL, size INTEGER NOT NULL, blob BLOB NOT NULL)",
    "CREATE TABLE IF NOT EXISTS user_sync_queue(id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER NOT NULL, "
    "created_at REAL NOT NULL, op_json TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS user_sync_queue_tg ON user_sync_queue(tg_id, id)",
    "CREATE TABLE IF NOT EXISTS auth_links(nonce_hash TEXT PRIMARY KEY, challenge TEXT NOT NULL, state TEXT NOT NULL, "
    "created REAL NOT NULL, tg_id INTEGER, key_plain TEXT, tries INTEGER NOT NULL DEFAULT 0)",
)

AUTH_TTL = 120
AUTH_MAX_ROWS = 5000
AUTH_START_PER_HOUR = 30             # на один адрес
AUTH_POLL_PER_HOUR = 900             # опросов на один адрес (приложение опрашивает раз в 2 с, до ~70 раз за вход)
AUTH_POLL_PER_NONCE = 150            # опросов одной ссылки за её жизнь
NONCE_RX = re.compile(r"^[A-Za-z0-9_-]{16,59}$")       # у параметра start в Telegram не больше 64 символов, 5 из них занимает «auth_»


class SyncError(Exception):
    def __init__(self, code, error, extra=None):
        Exception.__init__(self, error)
        self.code, self.error, self.extra = code, error, extra or {}


def _b64d(s):
    try:
        return base64.b64decode(s.encode("ascii"), validate=True)
    except (binascii.Error, ValueError, UnicodeEncodeError, AttributeError):
        raise SyncError(400, "bad_blob")


class SyncStore:
    """Таблицы живут в общей базе бота (keys.sqlite): так /delete в боте стирает и облачную копию, а подтверждение очереди
    и новая версия блока идут одной транзакцией. Соединение на поток."""

    def __init__(self, path, clock=time.time):
        self.path, self.clock = path, clock
        self._local = threading.local()
        self._ready = False
        self._lk, self._push, self._starts, self._polls, self._polls_n = threading.Lock(), {}, {}, {}, {}

    def conn(self):
        c = getattr(self._local, "c", None)
        if c is None:
            c = sqlite3.connect("file:%s?mode=rw" % quote(self.path.replace("\\", "/"), safe="/:"), uri=True, timeout=5,
                                isolation_level=None, check_same_thread=False)
            c.execute("PRAGMA busy_timeout=5000")
            self._local.c = c
        if not self._ready:
            for q in SCHEMA:
                c.execute(q)
            self._ready = True
        return c

    # ───── облачная копия ─────
    @staticmethod
    def _meta(r, queue_n=0):
        return {"exists": True, "rev": r[0], "sha256": r[1], "updated_at": r[2], "device": r[3], "salt": r[4], "size": r[5],
                "queue": queue_n}

    def _queue(self, c, tg_id, limit=QUEUE_MAX):
        c.execute("DELETE FROM user_sync_queue WHERE tg_id=? AND created_at<?", (tg_id, self.clock() - QUEUE_TTL))
        out = []
        for qid, created, js in c.execute("SELECT id, created_at, op_json FROM user_sync_queue WHERE tg_id=? ORDER BY id LIMIT ?",
                                          (tg_id, limit)).fetchall():
            try:
                out.append({"id": qid, "created_at": created, "op": json.loads(js)})
            except ValueError:
                continue
        return out

    def meta(self, tg_id):
        c = self.conn()
        r = c.execute("SELECT rev, sha256, updated_at, device, salt, size FROM user_sync WHERE tg_id=?", (tg_id,)).fetchone()
        n = c.execute("SELECT COUNT(*) FROM user_sync_queue WHERE tg_id=?", (tg_id,)).fetchone()[0]
        return self._meta(r, n) if r else {"exists": False, "rev": 0, "queue": n}

    def pull(self, tg_id):
        """-> (метаданные, шифртекст base64 или None, очередь из бота)."""
        c = self.conn()
        r = c.execute("SELECT rev, sha256, updated_at, device, salt, size, blob FROM user_sync WHERE tg_id=?", (tg_id,)).fetchone()
        q = self._queue(c, tg_id)
        if not r:
            return {"exists": False, "rev": 0, "queue": len(q)}, None, q
        return self._meta(r[:6], len(q)), base64.b64encode(r[6]).decode("ascii"), q

    def rate_ok(self, tg_id):
        now = self.clock()
        with self._lk:
            xs = [t for t in self._push.get(tg_id, []) if now - t < 3600]
            if len(xs) >= PUSH_PER_HOUR:
                self._push[tg_id] = xs
                return False
            xs.append(now)
            if len(self._push) > 10000:
                self._push.clear()
            self._push[tg_id] = xs
            return True

    def push(self, tg_id, body):
        """Сохранить новую версию. body: {base_rev, device, sha256, salt, blob (base64), ack_queue_ids}. -> метаданные.
        При base_rev != rev бросает SyncError(409) с актуальной версией в extra."""
        if not isinstance(body, dict):
            raise SyncError(400, "bad_json")
        base = body.get("base_rev")
        if isinstance(base, bool) or not isinstance(base, int) or base < 0:
            raise SyncError(400, "bad_base_rev")
        device = str(body.get("device") or "")[:60]
        sha, salt = body.get("sha256"), body.get("salt")
        if not isinstance(sha, str) or not SHA_RX.match(sha):
            raise SyncError(400, "bad_sha256")
        if not isinstance(salt, str) or not SALT_RX.match(salt):
            raise SyncError(400, "bad_salt")
        blob = _b64d(body.get("blob") if isinstance(body.get("blob"), str) else "")
        if not blob:
            raise SyncError(400, "empty_blob")
        if len(blob) > MAX_BLOB:
            raise SyncError(413, "too_large", {"max": MAX_BLOB})
        if not hmac.compare_digest(hashlib.sha256(blob).hexdigest(), sha):
            raise SyncError(400, "sha_mismatch")
        ack = body.get("ack_queue_ids") or []
        if not isinstance(ack, list) or len(ack) > QUEUE_MAX or any(isinstance(i, bool) or not isinstance(i, int) for i in ack):
            raise SyncError(400, "bad_ack")
        now = self.clock()
        c = self.conn()
        c.execute("BEGIN IMMEDIATE")
        try:
            cur = c.execute("SELECT rev, salt FROM user_sync WHERE tg_id=?", (tg_id,)).fetchone()
            rev = cur[0] if cur else 0
            if base != rev:
                c.execute("ROLLBACK")
                meta, blob_b64, q = self.pull(tg_id)
                raise SyncError(409, "conflict", {"meta": meta, "blob": blob_b64, "queue": q})
            if cur and cur[1] != salt:
                raise SyncError(400, "salt_changed")      # соль задаётся один раз: иначе другие устройства не расшифруют
            if cur:
                c.execute("UPDATE user_sync SET rev=rev+1, sha256=?, updated_at=?, device=?, size=?, blob=? WHERE tg_id=?",
                          (sha, now, device, len(blob), blob, tg_id))
            else:
                c.execute("INSERT INTO user_sync(tg_id, rev, sha256, updated_at, device, salt, size, blob) VALUES(?,?,?,?,?,?,?,?)",
                          (tg_id, 1, sha, now, device, salt, len(blob), blob))
            for qid in ack:                        # подтверждение очереди идёт в той же транзакции, что и новая версия
                c.execute("DELETE FROM user_sync_queue WHERE id=? AND tg_id=?", (qid, tg_id))
            c.execute("COMMIT")
        except BaseException:
            try:
                c.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        return self.meta(tg_id)

    def delete(self, tg_id):
        """Стереть облачную копию и очередь. -> была ли копия."""
        c = self.conn()
        c.execute("BEGIN IMMEDIATE")
        try:
            n = c.execute("DELETE FROM user_sync WHERE tg_id=?", (tg_id,)).rowcount
            c.execute("DELETE FROM user_sync_queue WHERE tg_id=?", (tg_id,))
            c.execute("COMMIT")
        except BaseException:
            try:
                c.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        return bool(n)

    def queue_add(self, tg_id, op):
        """Для проверок: в бою эту таблицу пополняет бот. -> id."""
        c = self.conn()
        if c.execute("SELECT COUNT(*) FROM user_sync_queue WHERE tg_id=?", (tg_id,)).fetchone()[0] >= QUEUE_MAX:
            raise SyncError(429, "queue_full")
        return c.execute("INSERT INTO user_sync_queue(tg_id, created_at, op_json) VALUES(?,?,?)",
                         (tg_id, self.clock(), json.dumps(op, ensure_ascii=False))).lastrowid

    # ───── вход в один клик ─────
    def auth_rate_ok(self, ip):
        now = self.clock()
        with self._lk:
            xs = [t for t in self._starts.get(ip, []) if now - t < 3600]
            if len(xs) >= AUTH_START_PER_HOUR:
                self._starts[ip] = xs
                return False
            xs.append(now)
            if len(self._starts) > 10000:
                self._starts.clear()
            self._starts[ip] = xs
            return True

    def poll_rate_ok(self, ip, nh):
        """Ограничение опросов: на адрес за час и на одну ссылку за её жизнь (опрос не должен нагружать базу)."""
        now = self.clock()
        with self._lk:
            if ip is not None:
                xs = [t for t in self._polls.get(ip, []) if now - t < 3600]
                ok = len(xs) < AUTH_POLL_PER_HOUR
                if ok:
                    xs.append(now)
                if len(self._polls) > 10000:
                    self._polls.clear()
                self._polls[ip] = xs
                if not ok:
                    return False
            ns = [t for t in self._polls_n.get(nh, []) if now - t < AUTH_TTL * 2]
            if len(ns) >= AUTH_POLL_PER_NONCE:
                self._polls_n[nh] = ns
                return False
            ns.append(now)
            if len(self._polls_n) > 20000:
                self._polls_n.clear()
            self._polls_n[nh] = ns
            return True

    @staticmethod
    def _nh(nonce):
        return hashlib.sha256(nonce.encode("utf-8")).hexdigest()

    def auth_start(self, nonce, challenge):
        """Приложение создаёт ожидающую ссылку: нонс (идёт в ссылку бота) и хеш секрета verifier (остаётся на компьютере)."""
        if not isinstance(nonce, str) or not NONCE_RX.match(nonce) or not isinstance(challenge, str) or not SHA_RX.match(challenge):
            raise SyncError(400, "bad_request")
        c = self.conn()
        c.execute("DELETE FROM auth_links WHERE created<?", (self.clock() - AUTH_TTL * 2,))
        if c.execute("SELECT COUNT(*) FROM auth_links").fetchone()[0] >= AUTH_MAX_ROWS:
            raise SyncError(429, "busy")
        try:
            c.execute("INSERT INTO auth_links(nonce_hash, challenge, state, created) VALUES(?,?,?,?)",
                      (self._nh(nonce), challenge, "pending", self.clock()))
        except sqlite3.IntegrityError:
            raise SyncError(409, "nonce_used")
        return {"ttl": AUTH_TTL}

    def auth_poll(self, nonce, verifier, ip=None):
        """-> {"state": pending | approved | expired, "key"}. Ключ выдаётся один раз: строка становится consumed, ключ стирается."""
        if not isinstance(nonce, str) or not NONCE_RX.match(nonce) or not isinstance(verifier, str) or not 16 <= len(verifier) <= 128:
            raise SyncError(400, "bad_request")
        try:
            vhash = hashlib.sha256(verifier.encode("utf-8")).hexdigest()
        except UnicodeEncodeError:                                  # одинокие суррогаты в JSON: это не наш verifier
            raise SyncError(400, "bad_request")
        nh = self._nh(nonce)
        if not self.poll_rate_ok(ip, nh):
            raise SyncError(429, "rate_limit")
        c = self.conn()
        if c.execute("SELECT 1 FROM auth_links WHERE nonce_hash=?", (nh,)).fetchone() is None:
            return {"state": "expired"}                             # нет ссылки: блокировку записи не берём
        c.execute("BEGIN IMMEDIATE")
        err = None
        try:
            r = c.execute("SELECT challenge, state, created, key_plain, tries FROM auth_links WHERE nonce_hash=?", (nh,)).fetchone()
            out = {"state": "expired"}
            if r:
                if not hmac.compare_digest(vhash, r[0]):
                    if r[4] + 1 >= 5:                                   # подбор секрета: гасим ссылку
                        c.execute("DELETE FROM auth_links WHERE nonce_hash=?", (nh,))
                    else:
                        c.execute("UPDATE auth_links SET tries=tries+1 WHERE nonce_hash=?", (nh,))
                    err = SyncError(403, "bad_verifier")
                elif self.clock() - r[2] > AUTH_TTL or r[1] == "consumed":
                    c.execute("DELETE FROM auth_links WHERE nonce_hash=?", (nh,))
                elif r[1] == "approved" and r[3]:
                    c.execute("UPDATE auth_links SET state='consumed', key_plain=NULL WHERE nonce_hash=?", (nh,))
                    out = {"state": "approved", "key": r[3]}
                else:
                    out = {"state": "pending"}
            c.execute("COMMIT")
        except BaseException:
            try:
                c.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        if err:
            raise err
        return out
