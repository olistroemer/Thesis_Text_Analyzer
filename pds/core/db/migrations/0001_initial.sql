-- Initial schema (SDD §8.1, ADR-0006).
-- Single unified schema for local and merged databases; append-only
-- history on module_runs / metric_values; current state via views.

CREATE TABLE sources (
    id               INTEGER PRIMARY KEY,
    name             TEXT NOT NULL UNIQUE,
    kind             TEXT NOT NULL CHECK (kind IN ('local', 'imported')),
    institution      TEXT,
    app_version      TEXT,
    schema_version   INTEGER,
    pipeline_summary TEXT,
    created_at       TEXT NOT NULL
);

CREATE TABLE theses (
    id             INTEGER PRIMARY KEY,
    source_id      INTEGER NOT NULL REFERENCES sources(id),
    pdf_sha256     TEXT NOT NULL,
    pdf_size_bytes INTEGER,
    pdf_path       TEXT,    -- PII; local only, stripped from exports (§8.3.1)
    pdf_filename   TEXT,    -- PII; local only, stripped from exports
    type           TEXT NOT NULL DEFAULT 'unspecified'
                   CHECK (type IN ('bachelor', 'master', 'unspecified')),
    language_hint  TEXT,
    excluded       INTEGER NOT NULL DEFAULT 0,
    notes          TEXT,    -- PII; stripped from exports
    tags           TEXT,    -- PII; stripped from exports
    added_at       TEXT NOT NULL,
    UNIQUE (source_id, pdf_sha256)
);

CREATE TABLE module_runs (
    id              INTEGER PRIMARY KEY,
    thesis_id       INTEGER NOT NULL REFERENCES theses(id),
    module_name     TEXT NOT NULL,
    module_version  TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('ok', 'na', 'error')),
    reason          TEXT,
    error_traceback TEXT,   -- may contain filesystem paths; stripped from exports
    started_at      TEXT NOT NULL,
    duration_ms     INTEGER
);

CREATE INDEX idx_module_runs_thesis_module
    ON module_runs (thesis_id, module_name, id);

CREATE TABLE metric_values (
    run_id      INTEGER NOT NULL REFERENCES module_runs(id),
    metric_name TEXT NOT NULL,
    value_num   REAL,
    value_text  TEXT,
    PRIMARY KEY (run_id, metric_name)
);

-- Latest artefact per (thesis, kind); older files stay on disk but are
-- not referenced (append-only history lives in module_runs).
CREATE TABLE artefact_files (
    thesis_id     INTEGER NOT NULL REFERENCES theses(id),
    kind          TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    run_id        INTEGER NOT NULL REFERENCES module_runs(id),
    PRIMARY KEY (thesis_id, kind)
);

-- Full history; recency_rank = 1 is the current row (§8.1.1).
CREATE VIEW v_module_run_history AS
SELECT
    mr.id,
    mr.thesis_id,
    t.source_id,
    mr.module_name,
    mr.module_version,
    mr.status,
    mr.reason,
    mr.error_traceback,
    mr.started_at,
    mr.duration_ms,
    ROW_NUMBER() OVER (
        PARTITION BY mr.thesis_id, mr.module_name
        ORDER BY mr.id DESC
    ) AS recency_rank
FROM module_runs mr
JOIN theses t ON t.id = mr.thesis_id;

-- Latest invocation per (thesis, module) with its metric values; bound
-- by the data grid and the Report view (§8.1.1, ADR-0016).
CREATE VIEW v_current_metrics AS
SELECT
    h.thesis_id,
    h.source_id,
    h.module_name,
    h.module_version,
    h.id AS run_id,
    h.status,
    h.reason,
    h.started_at,
    h.duration_ms,
    mv.metric_name,
    mv.value_num,
    mv.value_text
FROM v_module_run_history h
LEFT JOIN metric_values mv ON mv.run_id = h.id
WHERE h.recency_rank = 1;
