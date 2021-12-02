with state as (
    select *
    from {{ ref('stg_eltool__state') }}
)
select
  s.state_id,
  s.state_code,
  s.state_name
from state s
