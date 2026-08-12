-- +goose Up
CREATE TABLE customers (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Only key_hash is ever trusted for auth. key_prefix is non-secret (first
-- few chars of the raw key) so an admin can identify a key in `usage`/
-- `revoke-key` output without ever storing the usable secret itself.
CREATE TABLE api_keys (
    id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    key_hash TEXT NOT NULL UNIQUE,
    key_prefix TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ
);
CREATE INDEX idx_api_keys_key_hash ON api_keys (key_hash);

CREATE TABLE usage_events (
    id BIGSERIAL PRIMARY KEY,
    api_key_id BIGINT NOT NULL REFERENCES api_keys(id),
    model TEXT NOT NULL,
    request_path TEXT NOT NULL,
    status_code INT NOT NULL,
    prompt_tokens INT,
    completion_tokens INT,
    total_tokens INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_usage_events_api_key_id ON usage_events (api_key_id);
CREATE INDEX idx_usage_events_created_at ON usage_events (created_at);

-- +goose Down
DROP TABLE usage_events;
DROP TABLE api_keys;
DROP TABLE customers;
