# Evidência da suíte backend (derivada dos junit XML; logs brutos de ~100 MB ficam fora do repositório)

| Execução | Commit | Testes | Falhas | Erros | Skips | Tempo (s) | SHA-256 do XML |
|---|---|---|---|---|---|---|---|
| baseline_e64d2f7_backend_only_extract | `e64d2f7` | 1790 | 22 | 2 | 26 | 559 | `1e5eca2941b2cca0…` |
| baseline_e64d2f7_full_tree | `e64d2f7` | 1790 | 2 | 2 | 25 | 557 | `c0bd91d2ff194cee…` |
| head_0ee5074 | `0ee5074` | 1915 | 2 | 2 | 25 | 499 | `4ce52ab7052b14ad…` |
| head_83c749e | `83c749e` | 1926 | 3 | 2 | 25 | 551 | `6d78acd8d350e750…` |
| head_8aedd8a | `8aedd8a` | 1929 | 2 | 2 | 25 | 657 | `1374bc5ecefa4aa5…` |

## Comparação baseline `e64d2f7` (árvore completa) x HEAD `8aedd8a`

**failing_in_baseline_and_final** (3)
- `tests.test_context_builder::test_awaiting_approval_goals_are_excluded_from_context`
- `tests.test_context_builder::test_goal_lookup_failure_does_not_block_context_building`
- `tests.test_groq_stt::test_audio_vazio_ou_grande_demais_nem_chega_a_rede[xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

**failing_only_in_final (regressions)** (0)
- (nenhum)

**failing_only_in_baseline (fixed)** (0)
- (nenhum)

## Falhas por execução
### baseline_e64d2f7_backend_only_extract
- failure: `tests.test_auth::test_request_password_reset_enforces_a_minimum_response_time` — assert 0.09399999998277053 >= 0.1
- failure: `tests.test_ci_require_postgres::test_o_job_do_ci_liga_a_guarda_nos_dois_passos` — FileNotFoundError: [Errno 2] No such file or directory: 'C:\\Users\\dario\\.venvs\\baseline-e64d2f7\\.github\\workflows\\ci.yml'
- failure: `tests.test_context_builder::test_awaiting_approval_goals_are_excluded_from_context` — AssertionError: assert 'goal' not in {'goal', 'whatsapp'} + where {'goal', 'whatsapp'} = _sources(<orchestrator.context.Context object at 0x000001C32A682B10>)
- failure: `tests.test_context_builder::test_goal_lookup_failure_does_not_block_context_building` — AssertionError: assert 'goal' not in {'goal', 'whatsapp'} + where {'goal', 'whatsapp'} = _sources(<orchestrator.context.Context object at 0x000001C32A44BC50>)
- error: `tests.test_groq_stt::test_audio_vazio_ou_grande_demais_nem_chega_a_rede[xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` — failed on setup with "ValueError: the environment variable is longer than 32767 characters"
- failure: `tests.test_monitoring_integration.TestAlertmanagerConfiguration::test_alertmanager_file_exists` — AssertionError: alertmanager.yml not found assert False + where False = <built-in function _path_exists>('C:\\Users\\dario\\.venvs\\baseline-e64d2f7\\backend\\t
- failure: `tests.test_monitoring_integration.TestAlertmanagerConfiguration::test_alertmanager_grouping_configured` — AssertionError: alertmanager.yml not found assert False + where False = <built-in function _path_exists>('C:\\Users\\dario\\.venvs\\baseline-e64d2f7\\backend\\t
- failure: `tests.test_monitoring_integration.TestAlertmanagerConfiguration::test_alertmanager_has_routing_tree` — AssertionError: alertmanager.yml not found assert False + where False = <built-in function _path_exists>('C:\\Users\\dario\\.venvs\\baseline-e64d2f7\\backend\\t
- failure: `tests.test_monitoring_integration.TestAlertmanagerConfiguration::test_alertmanager_receivers_configured` — AssertionError: alertmanager.yml not found assert False + where False = <built-in function _path_exists>('C:\\Users\\dario\\.venvs\\baseline-e64d2f7\\backend\\t
- failure: `tests.test_monitoring_integration.TestDockerComposeConfiguration::test_alertmanager_service_defined` — AssertionError: docker-compose.yml not found assert False + where False = <built-in function _path_exists>('C:\\Users\\dario\\.venvs\\baseline-e64d2f7\\backend\
- failure: `tests.test_monitoring_integration.TestDockerComposeConfiguration::test_grafana_service_defined` — AssertionError: docker-compose.yml not found assert False + where False = <built-in function _path_exists>('C:\\Users\\dario\\.venvs\\baseline-e64d2f7\\backend\
- failure: `tests.test_monitoring_integration.TestDockerComposeConfiguration::test_monitoring_volumes_defined` — AssertionError: docker-compose.yml not found assert False + where False = <built-in function _path_exists>('C:\\Users\\dario\\.venvs\\baseline-e64d2f7\\backend\
- failure: `tests.test_monitoring_integration.TestDockerComposeConfiguration::test_prometheus_service_defined` — AssertionError: docker-compose.yml not found assert False + where False = <built-in function _path_exists>('C:\\Users\\dario\\.venvs\\baseline-e64d2f7\\backend\
- failure: `tests.test_monitoring_integration.TestDockerComposeConfiguration::test_services_use_internal_network` — AssertionError: docker-compose.yml not found assert False + where False = <built-in function _path_exists>('C:\\Users\\dario\\.venvs\\baseline-e64d2f7\\backend\
- failure: `tests.test_monitoring_integration.TestEnvironmentVariables::test_monitoring_env_vars_in_example` — AssertionError: .env.example not found assert False + where False = <built-in function _path_exists>('C:\\Users\\dario\\.venvs\\baseline-e64d2f7\\backend\\tests
- failure: `tests.test_monitoring_integration.TestGrafanaProvisioning::test_grafana_dashboard_provider_exists` — AssertionError: Grafana dashboard provider not found assert False + where False = <built-in function _path_exists>('C:\\Users\\dario\\.venvs\\baseline-e64d2f7\\
- failure: `tests.test_monitoring_integration.TestGrafanaProvisioning::test_grafana_datasource_points_to_prometheus` — AssertionError: Grafana datasource provisioning not found assert False + where False = <built-in function _path_exists>('C:\\Users\\dario\\.venvs\\baseline-e64d
- failure: `tests.test_monitoring_integration.TestGrafanaProvisioning::test_grafana_datasource_provisioning_exists` — AssertionError: Grafana datasource provisioning not found assert False + where False = <built-in function _path_exists>('C:\\Users\\dario\\.venvs\\baseline-e64d
- failure: `tests.test_monitoring_integration.TestGrafanaProvisioning::test_grafana_has_five_dashboards` — AssertionError: Dashboard 'system-health.json' not found assert False + where False = <built-in function _path_exists>('C:\\Users\\dario\\.venvs\\baseline-e64d2
- failure: `tests.test_monitoring_integration.TestPrometheusConfiguration::test_alert_rules_define_required_alerts` — AssertionError: alert_rules.yml not found assert False + where False = <built-in function _path_exists>('C:\\Users\\dario\\.venvs\\baseline-e64d2f7\\backend\\te
- failure: `tests.test_monitoring_integration.TestPrometheusConfiguration::test_alert_rules_file_exists` — AssertionError: alert_rules.yml not found assert False + where False = <built-in function _path_exists>('C:\\Users\\dario\\.venvs\\baseline-e64d2f7\\backend\\te
- failure: `tests.test_monitoring_integration.TestPrometheusConfiguration::test_prometheus_retention_policy_configured` — AssertionError: docker-compose.yml not found assert False + where False = <built-in function _path_exists>('C:\\Users\\dario\\.venvs\\baseline-e64d2f7\\backend\
- failure: `tests.test_monitoring_integration.TestPrometheusConfiguration::test_prometheus_scrape_interval_is_15_seconds` — AssertionError: prometheus.yml not found assert False + where False = <built-in function _path_exists>('C:\\Users\\dario\\.venvs\\baseline-e64d2f7\\backend\\tes

### baseline_e64d2f7_full_tree
- failure: `tests.test_context_builder::test_awaiting_approval_goals_are_excluded_from_context` — AssertionError: assert 'goal' not in {'goal', 'whatsapp'} + where {'goal', 'whatsapp'} = _sources(<orchestrator.context.Context object at 0x0000026390083F80>)
- failure: `tests.test_context_builder::test_goal_lookup_failure_does_not_block_context_building` — AssertionError: assert 'goal' not in {'goal', 'whatsapp'} + where {'goal', 'whatsapp'} = _sources(<orchestrator.context.Context object at 0x00000263900CB680>)
- error: `tests.test_groq_stt::test_audio_vazio_ou_grande_demais_nem_chega_a_rede[xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` — failed on setup with "ValueError: the environment variable is longer than 32767 characters"

### head_0ee5074
- failure: `tests.test_context_builder::test_awaiting_approval_goals_are_excluded_from_context` — AssertionError: assert 'goal' not in {'goal', 'whatsapp'} + where {'goal', 'whatsapp'} = _sources(<orchestrator.context.Context object at 0x000001B934D59100>)
- failure: `tests.test_context_builder::test_goal_lookup_failure_does_not_block_context_building` — AssertionError: assert 'goal' not in {'goal', 'whatsapp'} + where {'goal', 'whatsapp'} = _sources(<orchestrator.context.Context object at 0x000001B93352AF60>)
- error: `tests.test_groq_stt::test_audio_vazio_ou_grande_demais_nem_chega_a_rede[xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` — failed on setup with "ValueError: the environment variable is longer than 32767 characters"

### head_83c749e
- failure: `tests.test_context_builder::test_awaiting_approval_goals_are_excluded_from_context` — AssertionError: assert 'goal' not in {'goal', 'whatsapp'} + where {'goal', 'whatsapp'} = _sources(<orchestrator.context.Context object at 0x0000026FCBB6AF90>)
- failure: `tests.test_context_builder::test_goal_lookup_failure_does_not_block_context_building` — AssertionError: assert 'goal' not in {'goal', 'whatsapp'} + where {'goal', 'whatsapp'} = _sources(<orchestrator.context.Context object at 0x0000026FCE2E6A20>)
- failure: `tests.test_darius_whatsapp_contract::test_real_darius_idempotency_a_duplicate_message_does_not_create_a_second_task` — AssertionError: assert (1 == 1 and 2 == 1) + where 1 = len([<models.darius_whatsapp_task.DariusWhatsAppTask object at 0x0000026FCF751310>]) + and 2 = len([('551
- error: `tests.test_groq_stt::test_audio_vazio_ou_grande_demais_nem_chega_a_rede[xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` — failed on setup with "ValueError: the environment variable is longer than 32767 characters"

### head_8aedd8a
- failure: `tests.test_context_builder::test_awaiting_approval_goals_are_excluded_from_context` — AssertionError: assert 'goal' not in {'goal', 'whatsapp'} + where {'goal', 'whatsapp'} = _sources(<orchestrator.context.Context object at 0x00000224A4C2A8A0>)
- failure: `tests.test_context_builder::test_goal_lookup_failure_does_not_block_context_building` — AssertionError: assert 'goal' not in {'goal', 'whatsapp'} + where {'goal', 'whatsapp'} = _sources(<orchestrator.context.Context object at 0x00000224A4F27DA0>)
- error: `tests.test_groq_stt::test_audio_vazio_ou_grande_demais_nem_chega_a_rede[xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` — failed on setup with "ValueError: the environment variable is longer than 32767 characters"
