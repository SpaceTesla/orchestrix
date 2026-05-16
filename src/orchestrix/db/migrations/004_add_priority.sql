ALTER TABLE jobs
ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'
CHECK (priority IN ('high', 'normal', 'low'));
