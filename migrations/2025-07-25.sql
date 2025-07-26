-- 创建自定义枚举类型 resolver_type
CREATE TYPE resolver_type AS ENUM ('image', 'image_url', 'text', 'json');

-- 创建自定义枚举类型 storage_type
CREATE TYPE storage_type AS ENUM ('url');

-- 创建 storages 表
CREATE TABLE storages (
    name VARCHAR(64) PRIMARY KEY,
    nickname VARCHAR(255),
    type storage_type NOT NULL
);

-- 创建 blocks 表
CREATE TABLE blocks (
    id SERIAL PRIMARY KEY,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    storage VARCHAR(64) REFERENCES storages(name),
    resolver resolver_type NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(1024)
);

-- 创建 relations 表
CREATE TABLE relations (
    id SERIAL PRIMARY KEY,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    from_ INTEGER NOT NULL REFERENCES blocks(id),
    to_ INTEGER NOT NULL REFERENCES blocks(id),
    content TEXT NOT NULL
);