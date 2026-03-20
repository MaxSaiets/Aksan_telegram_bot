-- ============================================================
-- Run this in Supabase SQL Editor (Dashboard -> SQL Editor)
-- ============================================================

-- Videos (stores processed video records + deduplication key)
CREATE TABLE IF NOT EXISTS videos (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id       VARCHAR(50) NOT NULL,
    caption       TEXT,
    original_url  TEXT,
    youtube_url   TEXT,
    status        VARCHAR(20) NOT NULL DEFAULT 'pending',
    error_message TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Products (matched SKUs with Rozetka/SalesDrive cross-reference)
CREATE TABLE IF NOT EXISTS products (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id                UUID REFERENCES videos(id) ON DELETE CASCADE,
    model_name              TEXT NOT NULL,
    product_name            TEXT,
    sku                     VARCHAR(100),
    salesdrive_product_id   VARCHAR(100),
    rozetka_product_id      VARCHAR(100),
    rozetka_url             TEXT,
    youtube_url             TEXT,
    match_confidence        FLOAT DEFAULT 0.0,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

-- Photo metadata (append-only, archived JPG files stay on disk)
CREATE TABLE IF NOT EXISTS photo_batches (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_chat_id      VARCHAR(50) NOT NULL,
    target_chat_id      VARCHAR(50) NOT NULL,
    code                TEXT NOT NULL,
    model_code          TEXT,
    category            TEXT,
    caption_message_id  BIGINT,
    photo_count         INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS photo_items (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id            UUID NOT NULL REFERENCES photo_batches(id) ON DELETE CASCADE,
    photo_index         INTEGER NOT NULL,
    source_file_id      TEXT,
    target_message_id   BIGINT,
    archive_path        TEXT NOT NULL,
    filename            TEXT NOT NULL,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_videos_status           ON videos(status);
CREATE INDEX IF NOT EXISTS idx_videos_chat             ON videos(chat_id);
CREATE INDEX IF NOT EXISTS idx_videos_orig_url         ON videos(original_url);
CREATE INDEX IF NOT EXISTS idx_products_sku            ON products(sku);
CREATE INDEX IF NOT EXISTS idx_products_video          ON products(video_id);
CREATE INDEX IF NOT EXISTS idx_photo_batches_model     ON photo_batches(model_code);
CREATE INDEX IF NOT EXISTS idx_photo_batches_code      ON photo_batches(code);
CREATE INDEX IF NOT EXISTS idx_photo_items_batch       ON photo_items(batch_id);
CREATE INDEX IF NOT EXISTS idx_photo_items_message     ON photo_items(target_message_id);

-- Auto-update updated_at trigger
CREATE OR REPLACE FUNCTION _update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_videos_updated_at ON videos;
CREATE TRIGGER trg_videos_updated_at
    BEFORE UPDATE ON videos
    FOR EACH ROW EXECUTE FUNCTION _update_updated_at();

DROP TRIGGER IF EXISTS trg_products_updated_at ON products;
CREATE TRIGGER trg_products_updated_at
    BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION _update_updated_at();
