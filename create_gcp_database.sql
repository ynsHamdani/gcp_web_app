-- ============================================================
-- Historical Map GCP Application - PostgreSQL Database
-- ============================================================
--
-- psql script: creates the database and the core schema.
--
-- Tables:
--   users   - students and administrators
--   layers  - reference, historical, and basemap layer instances
--   gcps    - Ground Control Points, HASH-partitioned by
--             historical_layer_id
--
-- Authorization/deletion rules are handled by the backend,
-- not by PostgreSQL Row-Level Security.
--
-- ============================================================

-- ------------------------------------------------------------
-- 1. Create database if it does not already exist
-- ------------------------------------------------------------
-- This first section uses psql commands. Run the file with psql.

SELECT 'CREATE DATABASE gcp_web_app'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'gcp_web_app'
)\gexec

\connect gcp_web_app

-- ------------------------------------------------------------
-- 2. USERS
-- ------------------------------------------------------------
-- One table for both students and administrators.
-- Store only a secure password hash, never a plaintext password.

CREATE TABLE IF NOT EXISTS users (
    user_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username       VARCHAR(100) NOT NULL,
    email          VARCHAR(320) NOT NULL,
    password_hash  TEXT NOT NULL,
    user_role           VARCHAR(20) NOT NULL
                   CHECK (user_role IN ('student', 'admin')),
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_users_username UNIQUE (username),
    CONSTRAINT uq_users_email UNIQUE (email)
);

-- ------------------------------------------------------------
-- 3. LAYERS
-- ------------------------------------------------------------
-- One table represents uploaded reference layers, uploaded
-- historical layers, and basemap reference instances.
--
-- Examples:
--   uploaded reference -> layer_type='reference', source_type='uploaded'
--   basemap             -> layer_type='reference', source_type='basemap'
--   historical raster   -> layer_type='historical', source_type='uploaded'
--
-- A basemap gets a normal layer_id, so GCP reference_layer_id
-- never has to be NULL.
--
-- Extent values are expressed in the layer CRS stored in "crs".
-- sha256 is NULL for sources such as basemaps that have no file hash.
-- width/height are NULL for sources without fixed raster dimensions.

CREATE TABLE IF NOT EXISTS layers (
    layer_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    layer_type     VARCHAR(20) NOT NULL
                   CHECK (layer_type IN ('reference', 'historical')),
    source_type    VARCHAR(20) NOT NULL
                   CHECK (source_type IN ('uploaded', 'basemap')),
    layer_filename       TEXT NOT NULL,
    sha256         CHAR(64),
    crs            VARCHAR(64) NOT NULL,

    extent_xmin    DOUBLE PRECISION,
    extent_ymin    DOUBLE PRECISION,
    extent_xmax    DOUBLE PRECISION,
    extent_ymax    DOUBLE PRECISION,

    width          INTEGER,
    height         INTEGER,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_layers_sha256 UNIQUE (sha256),

    CONSTRAINT ck_layers_extent
        CHECK (
            (extent_xmin IS NULL AND extent_ymin IS NULL
             AND extent_xmax IS NULL AND extent_ymax IS NULL)
            OR
            (
                extent_xmin IS NOT NULL
                AND extent_ymin IS NOT NULL
                AND extent_xmax IS NOT NULL
                AND extent_ymax IS NOT NULL
                AND extent_xmin <= extent_xmax
                AND extent_ymin <= extent_ymax
            )
        ),

    CONSTRAINT ck_layers_dimensions
        CHECK (
            (width IS NULL AND height IS NULL)
            OR
            (
                width IS NOT NULL
                AND height IS NOT NULL
                AND width > 0
                AND height > 0
            )
        ),

    CONSTRAINT ck_uploaded_layer_metadata
        CHECK (
            source_type <> 'uploaded'
            OR (
                sha256 IS NOT NULL
                AND width IS NOT NULL
                AND height IS NOT NULL
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_layers_type
    ON layers (layer_type);

CREATE INDEX IF NOT EXISTS idx_layers_source_type
    ON layers (source_type);

CREATE INDEX IF NOT EXISTS idx_layers_sha256
    ON layers (sha256);

-- ------------------------------------------------------------
-- 4. GCPS
-- ------------------------------------------------------------
-- Each GCP fundamentally records:
--   historical raster pixel/line  <->  reference ground X/Y
--
-- Additional historical X/Y/lon/lat values are retained for QC.
-- No reference pixel/line is stored.
--
-- Both layer FKs are mandatory. A basemap is simply another row
-- in layers, so reference_layer_id does not need to be nullable.
--
-- The table is HASH-partitioned on historical_layer_id.
-- Sixteen partitions provide a moderate starting point; the
-- application can use gcps normally without knowing the partition.

CREATE TABLE IF NOT EXISTS gcps (
    gcp_id                BIGINT GENERATED ALWAYS AS IDENTITY,
    student_id            BIGINT NOT NULL,
    reference_layer_id    BIGINT NOT NULL,
    historical_layer_id   BIGINT NOT NULL,

    -- Authoritative reference ground coordinates.
    reference_x           DOUBLE PRECISION NOT NULL,
    reference_y           DOUBLE PRECISION NOT NULL,
    reference_lon         DOUBLE PRECISION NOT NULL,
    reference_lat         DOUBLE PRECISION NOT NULL,

    -- Historical raster coordinates used by GDAL GCPs.
    historical_pixel      DOUBLE PRECISION NOT NULL,
    historical_line       DOUBLE PRECISION NOT NULL,

    -- Historical position from the existing map georeferencing,
    -- retained for quality control/audit.
    historical_x          DOUBLE PRECISION NOT NULL,
    historical_y          DOUBLE PRECISION NOT NULL,
    historical_lon        DOUBLE PRECISION NOT NULL,
    historical_lat        DOUBLE PRECISION NOT NULL,

    crs                   VARCHAR(64) NOT NULL DEFAULT 'EPSG:25832',
    offset_m              DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    gcp_status                VARCHAR(20) NOT NULL DEFAULT 'confirmed'
                          CHECK (gcp_status IN ('pending', 'confirmed')),
    recorded_at           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_gcps
        PRIMARY KEY (historical_layer_id, gcp_id),

    CONSTRAINT fk_gcps_student
        FOREIGN KEY (student_id)
        REFERENCES users (user_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    CONSTRAINT fk_gcps_reference_layer
        FOREIGN KEY (reference_layer_id)
        REFERENCES layers (layer_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    CONSTRAINT fk_gcps_historical_layer
        FOREIGN KEY (historical_layer_id)
        REFERENCES layers (layer_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    CONSTRAINT ck_gcps_different_layers
        CHECK (reference_layer_id <> historical_layer_id),

    CONSTRAINT ck_gcps_reference_lat
        CHECK (reference_lat BETWEEN -90.0 AND 90.0),

    CONSTRAINT ck_gcps_reference_lon
        CHECK (reference_lon BETWEEN -180.0 AND 180.0),

    CONSTRAINT ck_gcps_historical_lat
        CHECK (historical_lat BETWEEN -90.0 AND 90.0),

    CONSTRAINT ck_gcps_historical_lon
        CHECK (historical_lon BETWEEN -180.0 AND 180.0),

    CONSTRAINT ck_gcps_pixel
        CHECK (historical_pixel >= 0.0),

    CONSTRAINT ck_gcps_line
        CHECK (historical_line >= 0.0),

    CONSTRAINT ck_gcps_offset
        CHECK (offset_m >= 0.0)
)
PARTITION BY HASH (historical_layer_id);

-- ------------------------------------------------------------
-- 5. GCP HASH PARTITIONS
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS gcps_p00
    PARTITION OF gcps
    FOR VALUES WITH (MODULUS 16, REMAINDER 0);

CREATE TABLE IF NOT EXISTS gcps_p01
    PARTITION OF gcps
    FOR VALUES WITH (MODULUS 16, REMAINDER 1);

CREATE TABLE IF NOT EXISTS gcps_p02
    PARTITION OF gcps
    FOR VALUES WITH (MODULUS 16, REMAINDER 2);

CREATE TABLE IF NOT EXISTS gcps_p03
    PARTITION OF gcps
    FOR VALUES WITH (MODULUS 16, REMAINDER 3);

CREATE TABLE IF NOT EXISTS gcps_p04
    PARTITION OF gcps
    FOR VALUES WITH (MODULUS 16, REMAINDER 4);

CREATE TABLE IF NOT EXISTS gcps_p05
    PARTITION OF gcps
    FOR VALUES WITH (MODULUS 16, REMAINDER 5);

CREATE TABLE IF NOT EXISTS gcps_p06
    PARTITION OF gcps
    FOR VALUES WITH (MODULUS 16, REMAINDER 6);

CREATE TABLE IF NOT EXISTS gcps_p07
    PARTITION OF gcps
    FOR VALUES WITH (MODULUS 16, REMAINDER 7);

CREATE TABLE IF NOT EXISTS gcps_p08
    PARTITION OF gcps
    FOR VALUES WITH (MODULUS 16, REMAINDER 8);

CREATE TABLE IF NOT EXISTS gcps_p09
    PARTITION OF gcps
    FOR VALUES WITH (MODULUS 16, REMAINDER 9);

CREATE TABLE IF NOT EXISTS gcps_p10
    PARTITION OF gcps
    FOR VALUES WITH (MODULUS 16, REMAINDER 10);

CREATE TABLE IF NOT EXISTS gcps_p11
    PARTITION OF gcps
    FOR VALUES WITH (MODULUS 16, REMAINDER 11);

CREATE TABLE IF NOT EXISTS gcps_p12
    PARTITION OF gcps
    FOR VALUES WITH (MODULUS 16, REMAINDER 12);

CREATE TABLE IF NOT EXISTS gcps_p13
    PARTITION OF gcps
    FOR VALUES WITH (MODULUS 16, REMAINDER 13);

CREATE TABLE IF NOT EXISTS gcps_p14
    PARTITION OF gcps
    FOR VALUES WITH (MODULUS 16, REMAINDER 14);

CREATE TABLE IF NOT EXISTS gcps_p15
    PARTITION OF gcps
    FOR VALUES WITH (MODULUS 16, REMAINDER 15);

-- ------------------------------------------------------------
-- 6. GCP INDEXES
-- ------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_gcps_reference_layer
    ON gcps (reference_layer_id);

CREATE INDEX IF NOT EXISTS idx_gcps_student
    ON gcps (student_id);

CREATE INDEX IF NOT EXISTS idx_gcps_historical_student
    ON gcps (historical_layer_id, student_id);

-- ------------------------------------------------------------
-- 7. OPTIONAL USER INSERT EXAMPLE
-- ------------------------------------------------------------
-- Do not insert real accounts automatically.
-- Create users from the authentication/backend layer using a
-- secure password hash.
--
-- INSERT INTO users (username, email, password_hash, role)
-- VALUES ('admin', 'admin@example.org', '<SECURE_PASSWORD_HASH>', 'admin');

-- ------------------------------------------------------------
-- 8. VERIFICATION COMMANDS (psql)
-- ------------------------------------------------------------
-- \dt
-- \d users
-- \d layers
-- \d gcps
--
-- SELECT inhrelid::regclass AS partition_name
-- FROM pg_inherits
-- WHERE inhparent = 'gcps'::regclass
-- ORDER BY 1;

-- ============================================================
-- END
-- ============================================================
