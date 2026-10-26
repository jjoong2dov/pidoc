<!-- pidoc-target: code -->
# CLI·설정 레퍼런스

이 문서의 값은 pimon 코드에서 뽑았습니다(`pidoc extract cli config http`).
코드가 바뀌면 `pidoc stale` 이 이 문서를 다시 보라고 알려 줍니다.

## 하위 명령

{{fact:pc:pimon.subcommands|join|code}}

`python3 -m pimon --help` 의 실제 출력:

```text pidoc-run=pimon_help target=pc
```

## 옵션

| 옵션 | 설명 |
|---|---|
| `--config` | {{fact:cli.pimon.option.config.help}} |
| `--root` | {{fact:cli.pimon.option.root.help}} |
| `--state-dir` | {{fact:cli.pimon.option.state-dir.help}} |

## 설정 키

설정 파일 견본은 `pimon.toml.example` 입니다. 빠진 값은 기본값을 씁니다.

| 키 | 기본값 | 설명 |
|---|---|---|
| `interval` | {{fact:config.interval.default}} | {{fact:config.interval.comment}} |
| `listen` | {{fact:config.listen.default|code}} | {{fact:config.listen.comment}} |
| `iface` | {{fact:config.iface.default|code}} | {{fact:config.iface.comment}} |
| `disk_path` | {{fact:config.disk_path.default|code}} | {{fact:config.disk_path.comment}} |
| `throttle_source` | {{fact:config.throttle_source.default|code}} | {{fact:config.throttle_source.comment}} |
| `limits.temp_warn` | {{fact:config.limits.temp_warn.default}} | {{fact:config.limits.temp_warn.comment}} |
| `limits.temp_crit` | {{fact:config.limits.temp_crit.default}} | |

기본값은 코드의 이 부분에서 옵니다.

```python pidoc-quote=pimon/config.py#L9-L26
```

## HTTP 주소

pimon 이 응답하는 주소: {{fact:http.get.paths|join|code}}
