CREATE TABLE IF NOT EXISTS alarm_queue_master (
    id bigserial PRIMARY KEY,
    composite varchar(150) NOT NULL,
    signal_type varchar(50) NOT NULL,
    trend_type varchar(50) NOT NULL,
    axis varchar(10) NOT NULL,
    priority varchar(20) NOT NULL,
    sensor_location varchar(200) NOT NULL,
    asset_id varchar(150) NOT NULL,
    org_id varchar(150),
    asset_name varchar(200),
    location_name varchar(200),
    company_name varchar(200),
    timestamp timestamptz NOT NULL,
    threshold_value double precision NOT NULL,
    observed_value double precision NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'pending',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    approved_by varchar(100),
    approved_at timestamptz,
    mail_sent_at timestamptz,
    notes text
);

CREATE TABLE IF NOT EXISTS asset_diagnostic_report_master (
    id bigserial PRIMARY KEY,
    asset_id varchar(150),
    trigger_source varchar(50) NOT NULL DEFAULT 'api',
    alarm_history_id bigint REFERENCES alarm_history_master(id) ON DELETE SET NULL,
    alarm_queue_id bigint REFERENCES alarm_queue_master(id) ON DELETE SET NULL,
    alarm_snapshot jsonb,
    diagnostic_input jsonb,
    report_json jsonb,
    response_json jsonb,
    result integer NOT NULL DEFAULT 0,
    status varchar(20) NOT NULL DEFAULT 'completed',
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS asset_diagnostic_report_master_asset_id_idx
    ON asset_diagnostic_report_master(asset_id);
