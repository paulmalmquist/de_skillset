import hashlib,json,re,subprocess,sys
from pathlib import Path
import yaml
import sqlglot
from flightcheck.cli import main
from flightcheck.evidence import EvidenceBundle
from flightcheck.modeling import ModelSpec
from flightcheck.policy import load_policy
from flightcheck.sql_audit import audit_sql

ROOT=Path(__file__).parents[1]


def test_cli_trace_returns_failure_for_mismatched_stage_population(capsys):
    assert main(['trace',str(ROOT/'examples/trace-stages.json'),'--keys','event_id'])==1


def test_catalog_matches_skills():
    subprocess.run([sys.executable,str(ROOT/'scripts/check_catalog.py')],check=True,capture_output=True)


def test_schemas_match_current_models():
    for file,model in [('evidence',EvidenceBundle),('model',ModelSpec)]:
        assert json.loads((ROOT/f'schemas/{file}.schema.json').read_text())==model.model_json_schema()


def test_worked_dbt_example_compiles_for_static_policy_checks():
    root=ROOT/'examples/dbt'
    metadata={m['name']:m for m in yaml.safe_load((root/'models/schema.yml').read_text())['models']}
    policy=load_policy(ROOT/'config/example-dbt-policy.yml')
    def relation(name):
        layer=metadata[name]['config']['meta']['flightcheck']['layer'] if name in metadata else 'raw'
        return f'synthetic.flightcheck_demo_{layer}.{name}'
    for path in (root/'models').rglob('*.sql'):
        compiled=re.sub(r"\{\{ ref\('([^']+)'\) \}\}",lambda m:relation(m[1]),path.read_text())
        sqlglot.parse_one(compiled,read='bigquery')
        layer=metadata[path.stem]['config']['meta']['flightcheck']['layer']
        assert audit_sql(compiled,layer,policy)['blocking']==0, path
    for path in (root/'tests').glob('*.sql'):
        compiled=re.sub(r"\{\{ ref\('([^']+)'\) \}\}",lambda m:relation(m[1]),path.read_text())
        sqlglot.parse_one(compiled,read='bigquery')


def test_hooks_emit_feedback_and_deny_unrecognized_query_shape():
    hook=ROOT/'scripts/claude_hook.py'
    def run(event):
        output=subprocess.run([sys.executable,str(hook)],input=json.dumps(event),text=True,capture_output=True,check=True)
        return json.loads(output.stdout) if output.stdout.strip() else {}
    deny=run({'hook_event_name':'PreToolUse','tool_input':{'query':'DROP TABLE x'}})
    assert deny['hookSpecificOutput']['permissionDecision']=='deny'
    unknown=run({'hook_event_name':'PreToolUse','tool_input':{'request':{}}})
    assert unknown['hookSpecificOutput']['permissionDecision']=='deny'
    assert run({'hook_event_name':'PreToolUse','tool_input':{'query':'SELECT 1'}})=={}
    feedback=run({'hook_event_name':'PostToolUse','tool_input':{'file_path':str(ROOT/'examples/legacy-consumer.sql')}})
    assert 'LAYER_BYPASS' in feedback['hookSpecificOutput']['additionalContext']
