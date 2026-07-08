-- TruthLayer migration 003: verdict feedback.
--
-- One row per thumbs-up/down a visitor leaves on a verdict. This is the raw
-- material for the post-launch usage analysis (Task 4.6).

create table if not exists verdict_feedback (
    id          uuid primary key default gen_random_uuid(),
    claim_text  text not null,
    verdict     text not null,
    helpful     boolean not null,
    created_at  timestamptz not null default now()
);

create index if not exists verdict_feedback_created_at_idx
    on verdict_feedback (created_at);

-- Default-deny, same reasoning as every other table.
alter table verdict_feedback enable row level security;
