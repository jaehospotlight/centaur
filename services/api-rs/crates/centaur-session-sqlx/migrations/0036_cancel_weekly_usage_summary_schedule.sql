-- Cancel the obsolete weekly usage summary workflow that posts
-- ":centaur: Weekly Centaur Usage Summary :centaur:" into the main Centaur
-- Slack channel. The workflow definition is persisted as an Absurd schedule
-- task, not as a checked-in Python workflow.

do $$
declare
  v_task_id uuid;
begin
  for v_task_id in
    select task_id
      from absurd.t_centaur_workflow_schedules
     where state not in ('completed', 'failed', 'cancelled')
       and (
         params::text ilike '%Weekly Centaur Usage Summary%'
         or (
           params::text ilike '%C0A82R7S80N%'
           and (
             params ->> 'schedule_id' ilike '%usage%'
             or params ->> 'workflow_name' ilike '%usage%'
             or params ->> 'name' ilike '%usage%'
           )
         )
       )
  loop
    perform absurd.cancel_task('centaur_workflow_schedules', v_task_id);
  end loop;
end;
$$;
