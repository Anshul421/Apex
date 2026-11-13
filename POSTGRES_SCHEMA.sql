CREATE TABLE facility_slots (
	id VARCHAR(64) NOT NULL, 
	facility VARCHAR(255) NOT NULL, 
	start_time TIMESTAMP WITH TIME ZONE NOT NULL, 
	duration_minutes INTEGER NOT NULL, 
	available BOOLEAN NOT NULL, 
	source_version VARCHAR(128) NOT NULL, 
	failure_mode VARCHAR(64), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_facility_slot UNIQUE (facility, start_time)
);

CREATE TABLE jobs (
	id VARCHAR(64) NOT NULL, 
	job_type VARCHAR(128) NOT NULL, 
	payload JSON NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	attempts INTEGER NOT NULL, 
	max_attempts INTEGER NOT NULL, 
	last_error TEXT, 
	available_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE ml_experiments (
	id VARCHAR(64) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	description TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE tenants (
	id VARCHAR(64) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE athletes (
	id VARCHAR(64) NOT NULL, 
	tenant_id VARCHAR(64) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	objective TEXT NOT NULL, 
	timezone_name VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE TABLE ml_runs (
	id VARCHAR(64) NOT NULL, 
	experiment_id VARCHAR(64) NOT NULL, 
	run_name VARCHAR(255) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	ended_at TIMESTAMP WITH TIME ZONE, 
	code_version VARCHAR(128) NOT NULL, 
	dataset_name VARCHAR(255) NOT NULL, 
	dataset_version VARCHAR(128) NOT NULL, 
	dataset_sha256 VARCHAR(64) NOT NULL, 
	feature_schema_version VARCHAR(128) NOT NULL, 
	random_seed INTEGER NOT NULL, 
	params JSON NOT NULL, 
	metrics JSON NOT NULL, 
	tags JSON NOT NULL, 
	artifact_uri TEXT, 
	selected_model VARCHAR(128), 
	decision TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(experiment_id) REFERENCES ml_experiments (id)
);

CREATE TABLE users (
	id VARCHAR(64) NOT NULL, 
	tenant_id VARCHAR(64) NOT NULL, 
	external_subject VARCHAR(255) NOT NULL, 
	email VARCHAR(320), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_user_tenant_subject UNIQUE (tenant_id, external_subject), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

CREATE TABLE matches (
	id VARCHAR(64) NOT NULL, 
	athlete_id VARCHAR(64) NOT NULL, 
	start_time TIMESTAMP WITH TIME ZONE NOT NULL, 
	venue VARCHAR(255) NOT NULL, 
	revision INTEGER NOT NULL, 
	source_version VARCHAR(128) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(athlete_id) REFERENCES athletes (id)
);

CREATE TABLE ml_model_versions (
	id VARCHAR(64) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	version INTEGER NOT NULL, 
	run_id VARCHAR(64) NOT NULL, 
	stage VARCHAR(32) NOT NULL, 
	alias VARCHAR(64), 
	artifact_uri TEXT NOT NULL, 
	model_format VARCHAR(64) NOT NULL, 
	input_schema JSON NOT NULL, 
	metrics JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_ml_model_name_version UNIQUE (name, version), 
	CONSTRAINT uq_ml_model_name_alias UNIQUE (name, alias), 
	FOREIGN KEY(run_id) REFERENCES ml_runs (id)
);

CREATE TABLE observations (
	id VARCHAR(64) NOT NULL, 
	athlete_id VARCHAR(64) NOT NULL, 
	source VARCHAR(32) NOT NULL, 
	observed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	source_version VARCHAR(128) NOT NULL, 
	payload JSON NOT NULL, 
	freshness VARCHAR(32) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_observation_source_version UNIQUE (athlete_id, source, source_version), 
	FOREIGN KEY(athlete_id) REFERENCES athletes (id)
);

CREATE TABLE plan_versions (
	id VARCHAR(64) NOT NULL, 
	athlete_id VARCHAR(64) NOT NULL, 
	version INTEGER NOT NULL, 
	parent_plan_id VARCHAR(64), 
	reason VARCHAR(128) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	world_state_hash VARCHAR(128) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	intent JSON NOT NULL, 
	diff JSON NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_plan_athlete_version UNIQUE (athlete_id, version), 
	FOREIGN KEY(athlete_id) REFERENCES athletes (id), 
	FOREIGN KEY(parent_plan_id) REFERENCES plan_versions (id)
);

CREATE TABLE agent_events (
	id VARCHAR(64) NOT NULL, 
	run_id VARCHAR(64) NOT NULL, 
	athlete_id VARCHAR(64) NOT NULL, 
	plan_id VARCHAR(64), 
	event_type VARCHAR(128) NOT NULL, 
	payload JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(athlete_id) REFERENCES athletes (id), 
	FOREIGN KEY(plan_id) REFERENCES plan_versions (id)
);

CREATE TABLE constraint_results (
	id VARCHAR(64) NOT NULL, 
	plan_id VARCHAR(64) NOT NULL, 
	constraint_type VARCHAR(128) NOT NULL, 
	limit_value FLOAT, 
	measured_value FLOAT, 
	passed BOOLEAN NOT NULL, 
	details JSON NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(plan_id) REFERENCES plan_versions (id)
);

CREATE TABLE sessions (
	id VARCHAR(64) NOT NULL, 
	plan_id VARCHAR(64) NOT NULL, 
	logical_key VARCHAR(128) NOT NULL, 
	session_type VARCHAR(128) NOT NULL, 
	start_time TIMESTAMP WITH TIME ZONE NOT NULL, 
	duration_minutes INTEGER NOT NULL, 
	intended_load INTEGER NOT NULL, 
	intensity VARCHAR(32) NOT NULL, 
	facility VARCHAR(255), 
	status VARCHAR(32) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_session_plan_logical_key UNIQUE (plan_id, logical_key), 
	FOREIGN KEY(plan_id) REFERENCES plan_versions (id)
);

CREATE TABLE tool_actions (
	id VARCHAR(64) NOT NULL, 
	athlete_id VARCHAR(64) NOT NULL, 
	plan_id VARCHAR(64), 
	action_key VARCHAR(128) NOT NULL, 
	tool VARCHAR(64) NOT NULL, 
	arguments JSON NOT NULL, 
	result JSON NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	status VARCHAR(32) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(athlete_id) REFERENCES athletes (id), 
	FOREIGN KEY(plan_id) REFERENCES plan_versions (id), 
	UNIQUE (action_key)
);

CREATE TABLE verification_runs (
	id VARCHAR(64) NOT NULL, 
	plan_id VARCHAR(64) NOT NULL, 
	state_snapshot JSON NOT NULL, 
	passed BOOLEAN NOT NULL, 
	violations JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(plan_id) REFERENCES plan_versions (id)
);

CREATE TABLE web_evidence (
	id VARCHAR(64) NOT NULL, 
	athlete_id VARCHAR(64) NOT NULL, 
	plan_id VARCHAR(64), 
	url TEXT NOT NULL, 
	retrieved_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	field VARCHAR(128) NOT NULL, 
	value JSON NOT NULL, 
	provenance JSON NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(athlete_id) REFERENCES athletes (id), 
	FOREIGN KEY(plan_id) REFERENCES plan_versions (id)
);

CREATE TABLE bookings (
	id VARCHAR(64) NOT NULL, 
	athlete_id VARCHAR(64) NOT NULL, 
	plan_id VARCHAR(64) NOT NULL, 
	session_id VARCHAR(64) NOT NULL, 
	action_key VARCHAR(128) NOT NULL, 
	facility VARCHAR(255) NOT NULL, 
	start_time TIMESTAMP WITH TIME ZONE NOT NULL, 
	duration_minutes INTEGER NOT NULL, 
	confirmation_code VARCHAR(128), 
	status VARCHAR(32) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(athlete_id) REFERENCES athletes (id), 
	FOREIGN KEY(plan_id) REFERENCES plan_versions (id), 
	FOREIGN KEY(session_id) REFERENCES sessions (id), 
	UNIQUE (action_key)
);

CREATE TABLE calendar_entries (
	id VARCHAR(64) NOT NULL, 
	athlete_id VARCHAR(64) NOT NULL, 
	plan_id VARCHAR(64) NOT NULL, 
	session_id VARCHAR(64) NOT NULL, 
	action_key VARCHAR(128) NOT NULL, 
	external_id VARCHAR(128) NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	start_time TIMESTAMP WITH TIME ZONE NOT NULL, 
	duration_minutes INTEGER NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(athlete_id) REFERENCES athletes (id), 
	FOREIGN KEY(plan_id) REFERENCES plan_versions (id), 
	FOREIGN KEY(session_id) REFERENCES sessions (id), 
	UNIQUE (action_key)
);

CREATE INDEX ix_facility_slots_facility ON facility_slots (facility);

CREATE INDEX ix_facility_slots_start_time ON facility_slots (start_time);

CREATE INDEX ix_jobs_job_type ON jobs (job_type);

CREATE INDEX ix_jobs_status ON jobs (status);

CREATE INDEX ix_athletes_tenant_id ON athletes (tenant_id);

CREATE INDEX ix_ml_runs_experiment_id ON ml_runs (experiment_id);

CREATE INDEX ix_ml_runs_experiment_started ON ml_runs (experiment_id, started_at);

CREATE INDEX ix_ml_runs_status ON ml_runs (status);

CREATE INDEX ix_users_tenant_id ON users (tenant_id);

CREATE INDEX ix_matches_athlete_id ON matches (athlete_id);

CREATE INDEX ix_ml_model_versions_alias ON ml_model_versions (alias);

CREATE INDEX ix_ml_model_versions_name ON ml_model_versions (name);

CREATE INDEX ix_ml_model_versions_name_created ON ml_model_versions (name, created_at);

CREATE INDEX ix_ml_model_versions_run_id ON ml_model_versions (run_id);

CREATE INDEX ix_ml_model_versions_stage ON ml_model_versions (stage);

CREATE INDEX ix_observation_athlete_source_time ON observations (athlete_id, source, observed_at);

CREATE INDEX ix_observations_athlete_id ON observations (athlete_id);

CREATE INDEX ix_observations_source ON observations (source);

CREATE INDEX ix_plan_athlete_created ON plan_versions (athlete_id, created_at);

CREATE INDEX ix_plan_versions_athlete_id ON plan_versions (athlete_id);

CREATE INDEX ix_agent_events_athlete_id ON agent_events (athlete_id);

CREATE INDEX ix_agent_events_plan_id ON agent_events (plan_id);

CREATE INDEX ix_agent_events_run_id ON agent_events (run_id);

CREATE INDEX ix_constraint_results_plan_id ON constraint_results (plan_id);

CREATE INDEX ix_sessions_plan_id ON sessions (plan_id);

CREATE INDEX ix_tool_action_plan_status ON tool_actions (plan_id, status);

CREATE INDEX ix_tool_actions_athlete_id ON tool_actions (athlete_id);

CREATE INDEX ix_tool_actions_plan_id ON tool_actions (plan_id);

CREATE INDEX ix_verification_runs_plan_id ON verification_runs (plan_id);

CREATE INDEX ix_web_evidence_athlete_id ON web_evidence (athlete_id);

CREATE INDEX ix_web_evidence_plan_id ON web_evidence (plan_id);

CREATE INDEX ix_bookings_athlete_id ON bookings (athlete_id);

CREATE INDEX ix_bookings_plan_id ON bookings (plan_id);

CREATE INDEX ix_bookings_session_id ON bookings (session_id);

CREATE INDEX ix_calendar_entries_athlete_id ON calendar_entries (athlete_id);

CREATE INDEX ix_calendar_entries_plan_id ON calendar_entries (plan_id);

CREATE INDEX ix_calendar_entries_session_id ON calendar_entries (session_id);
