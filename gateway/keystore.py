"""API key generation, validation, and usage logging against Postgres.

"""
from __future__ import annotations
import contextlib
import hashlib
import os
import secrets

import psycopg2
import psycopg2.extras

def _database_url() -> str:
    """DATABASE_URL wins if set (local dev). Otherwise compose from parts --
    used in the cluster, where DB_PASSWORD comes from a Secret via
    secretKeyRef and the rest are plain (non-secret) env vars."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    user = os.environ.get("DB_USER", "gateway")
    password = os.environ.get("DB_PASSWORD", "")
    name = os.environ.get("DB_NAME", "gateway")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


DATABASE_URL = _database_url()


@contextlib.contextmanager
def _cursor(dict_rows: bool = False):
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            cur_factory = psycopg2.extras.RealDictCursor if dict_rows else None
            with conn.cursor(cursor_factory=cur_factory) as cur:
                yield cur
    finally:
        conn.close()


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_key() -> str:
    return "sk-" + secrets.token_urlsafe(32)


def create_api_key(customer_name: str) -> str:
    """Creates the customer if new, issues a fresh key, returns the RAW key.
    The raw key is never stored -- only its hash. This is the one and only
    time it's ever available; the caller must save it now."""
    raw_key = generate_key()
    key_hash = hash_key(raw_key)
    key_prefix = raw_key[:11]  # "sk-" + 8 chars -- enough to identify, not to guess
    with _cursor() as cur:
        cur.execute(
            "INSERT INTO customers (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
            (customer_name,),
        )
        cur.execute("SELECT id FROM customers WHERE name = %s", (customer_name,))
        customer_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO api_keys (customer_id, key_hash, key_prefix) VALUES (%s, %s, %s)",
            (customer_id, key_hash, key_prefix),
        )
    return raw_key


def revoke_key(key_prefix: str) -> bool:
    with _cursor() as cur:
        cur.execute(
            "UPDATE api_keys SET revoked_at = now() "
            "WHERE key_prefix = %s AND revoked_at IS NULL",
            (key_prefix,),
        )
        return cur.rowcount > 0


def validate_key(raw_key: str) -> dict | None:
    """Returns {'api_key_id', 'customer_id', 'customer_name'} if the key is
    valid and not revoked, else None. Only ever compares hashes."""
    key_hash = hash_key(raw_key)
    with _cursor(dict_rows=True) as cur:
        cur.execute(
            """
            SELECT ak.id AS api_key_id, c.id AS customer_id, c.name AS customer_name
            FROM api_keys ak JOIN customers c ON c.id = ak.customer_id
            WHERE ak.key_hash = %s AND ak.revoked_at IS NULL
            """,
            (key_hash,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def log_usage(
    api_key_id: int,
    model: str,
    request_path: str,
    status_code: int,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
) -> None:
    with _cursor() as cur:
        cur.execute(
            """
            INSERT INTO usage_events
                (api_key_id, model, request_path, status_code,
                 prompt_tokens, completion_tokens, total_tokens)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (api_key_id, model, request_path, status_code,
             prompt_tokens, completion_tokens, total_tokens),
        )


def usage_summary(customer_name: str | None = None) -> list[dict]:
    query = """
        SELECT c.name AS customer, ue.model, COUNT(*) AS requests,
               SUM(ue.total_tokens) AS total_tokens
        FROM usage_events ue
        JOIN api_keys ak ON ak.id = ue.api_key_id
        JOIN customers c ON c.id = ak.customer_id
    """
    params: tuple = ()
    if customer_name:
        query += " WHERE c.name = %s"
        params = (customer_name,)
    query += " GROUP BY c.name, ue.model ORDER BY c.name, ue.model"
    with _cursor(dict_rows=True) as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]
