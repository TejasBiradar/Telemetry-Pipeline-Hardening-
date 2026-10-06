# Guarantees: web_analytics

> What the pipeline silently assumes. Each rule comes from static analysis of the code,
> and counts as a guarantee only after a person has confirmed it.
> Status: **0 confirmed**, 15 pending review, 0 rejected.

## Confirmed

_None yet._

## Pending review

| Kind | Field | What the code implies | Evidence |
|---|---|---|---|
| runtime_columns | - | a DataFrame is built from records: its column names come from the data, not the code; confirm them with a runtime run | `run.py:38` |
| timestamp_unit | event_ts | 'event_ts' is parsed as epoch time in 'ms' | `run.py:39` |
| dedup_key | event_id | rows with the same 'event_id' are treated as duplicates; later copies are dropped | `run.py:47` |
| required_field | user_id | rows with missing 'user_id' are removed: 'user_id' is treated as required | `run.py:50` |
| unit_conversion | duration_ms | 'duration_s' = df['duration_ms'] / 1000.0: assumes 'duration_ms' is in the unit that this factor (1000.0) converts from | `run.py:53` |
| row_filter | duration_s | 'df' keeps only rows where df['duration_s'] < 300; other rows are dropped silently | `run.py:56` |
| keyword_match | error_message | 'error_message' is classified by matching the text 'timeout': wording or language changes break it | `run.py:60` |
| string_format | client_version | 'client_version' is assumed to be text split by '.' | `run.py:63` |
| default_fill | session_id | missing values derived from 'session_id' are silently replaced with 'Other' | `run.py:79` |
| unmapped_to_null | session_id | 'session_id' is mapped with a fixed table of 5 values (session_001, session_002, session_003, session_004, session_005); any other value becomes missing | `run.py:79` |
| row_filter | action | 'page_views' keeps only rows where df['action'] == 'page_view'; other rows are dropped silently | `run.py:90` |
| group_key_drops_nulls | date | grouped by 'date' with pandas' default dropna=True: rows with missing 'date' vanish from the result | `run.py:92` |
| group_key_drops_nulls | platform | grouped by 'platform' with pandas' default dropna=True: rows with missing 'platform' vanish from the result | `run.py:92` |
| group_key_drops_nulls | country | grouped by 'country' with pandas' default dropna=True: rows with missing 'country' vanish from the result | `run.py:92` |
| unused_field | major_version | 'major_version' is created but never used later and never reaches an output | `run.py:63` |

## Rejected

_None._

## Observed behaviour on unusual input

> From the characterisation tests. Recorded as-is, not fixed.

- `normal`: runs and produces 18 output rows
- `single_event`: runs and produces 1 output rows
- `heavy_nulls`: runs and produces 17 output rows
- `all_users_null`: runs and produces 0 output rows
- `heavy_duplicates`: runs and produces 18 output rows
- `slow_loads`: runs and produces 18 output rows
- `empty`: the pipeline crashes with KeyError: 'event_ts'
