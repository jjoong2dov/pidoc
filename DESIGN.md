# pidoc 설계 (책 4권 replay 용 요약)

대상 저장소 안에 `docs/pidoc.toml` 과 폴더 몇 개를 두고 쓴다.

```
docs/pidoc.toml                 설정
docs/evidence/runs/<run-id>/    손대지 않은 실행 증거: manifest.json, <명령id>.stdout/.stderr(원시 바이트), <명령id>.json(argv·종료 코드·시간·잘림·sha256)
docs/facts/<대상>.json          증거에서 뽑은 사실 {키: {value, type, run, command, extract, source_sha256, collected_at}}
docs/src/*.md                   문서 원본({{fact:키}} 자리표시자)
docs/out/                       결과
```

종료 코드: 0 성공, 1 검사 실패(문서 문제), 2 사용법·설정 오류, 3 수집 실패.

## 1단계 — 로컬 수집기 (`pidoc collect`, `pidoc facts`)
설정 예:
```toml
[project]
name = "pimon"
root = ".."

[targets.pc]
kind = "local"
alias = "devpc"

[collect]
timeout_s = 20
max_output = 1048576
env_allow = ["PATH", "HOME", "LANG"]
env_set = { LC_ALL = "C.UTF-8" }

[[command]]
id = "python_version"
argv = ["python3", "--version"]
targets = ["pc"]
  [[command.fact]]
  key = "system.python_version"
  extract = "regex"          # stdout_all | stdout_line | regex | json
  pattern = 'Python (\S+)'
  type = "string"            # string | int | float | list | bool
```
- 셸 없이 argv 실행, 시간 초과, 출력 상한(넘으면 잘림 표시), 환경변수 허용 목록, stdout/stderr 원시 바이트 저장.
- 실패한 명령의 사실은 갱신하지 않는다. 잘린 출력에서는 사실을 만들지 않는다.

## 2단계 — ssh 대상과 가리기
- `kind = "ssh"`, `host = "pi@pi4.local"`(환경변수 PIDOC_TARGET_<이름> 으로 덮어씀), `known_hosts` 파일 지정.
- ssh 옵션: BatchMode=yes, StrictHostKeyChecking=yes. 원격 명령은 shlex.join 으로 한 줄. `allow_programs` 목록 밖 프로그램은 실행하지 않는다(보안 경계가 아니라 실수 방지).
- 가리기: 수집 직후 증거와 사실에서 IP·실제 호스트 이름(→ alias)·이 PC 홈 경로(→ ~)를 바꾼다.

## 3단계 — AI 초안 (`pidoc draft <틀.md> --out <파일> --ai claude|codex|none`)
- 틀 + 사실 목록(키·값)을 프롬프트로 만들어 `claude -p`(stdin) 또는 `codex exec -` 에 보낸다. none 이면 프롬프트만 저장.
- 호출 기록: docs/ai/<시각>-draft/ 에 prompt.txt, meta.json(도구·시각·종료 코드), raw.txt.
- 결과 본문에 숫자 리터럴이 있으면 그 줄을 보여 준다.

## 4단계 — 렌더와 숫자 검사 (`pidoc render`, `pidoc check --only facts numbers`)
- `{{fact:키}}`, `{{fact:대상:키|변환}}`(변환은 int, round1, join, code 만). 없는 사실·타입 불일치는 오류, 결과를 쓰지 않는다.
- 사실은 증거와 맞는지 확인한다(그 run 의 stdout 에서 같은 규칙으로 다시 뽑아 비교).
- 숫자 검사: docs/src 본문 숫자 리터럴은 오류. 머리글 번호, 번호 목록, 장·절 참조, `IPv4`·`UTF-8` 같은 이름, 줄 끝 `<!-- pidoc-ok: 이유 -->` 는 뺀다.

## 5단계 — 인용·출력 검사 (`pidoc check --only quote run`)
- ```` ```python pidoc-quote=경로#L10-L24 ```` : render 가 파일에서 채우고, check 가 실제 파일과 대조. 경로는 프로젝트 안만.
- ```` ```console pidoc-run=명령id ```` : 최신 증거의 stdout 으로 채우고, check 는 정규화([mask] 시각·호스트 이름·정규식) 뒤 비교.

## 6단계 — 내부 정보·낡은 문서 (`pidoc check --only secrets`, `pidoc stale`)
- secrets: IPv4·이메일·실제 호스트 이름·홈 폴더 경로·개인키 머리줄·금지어(docs/banned.txt)를 src·out·facts·evidence 에서 찾는다.
- stale: render 때 문서마다 쓴 원본 파일·사실의 sha256 을 docs/out/.deps.json 에 남기고, 지금과 다르면 "다시 볼 문서"로 보고.
