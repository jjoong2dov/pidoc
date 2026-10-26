# pidoc — 실행 증거로 쓰고 시험하는 기술문서

AI 가 기술문서를 빨리 쓰게 하되, **명령·출력·버전·수치는 실행 증거 없이는 출판되지 않게** 만드는 작은 파이썬 도구입니다.
전자책 《라즈베리 파이 × AI 실전 개발실》 4권의 실습 저장소이고, 2권의 pimon(라즈베리 파이 상태 모니터)을 문서화 대상으로 씁니다.

```
명령 실행 ──▶ evidence(손대지 않은 출력) ──▶ facts(타입 있는 값) ──▶ docs/src({{fact:키}}) ──▶ docs/out
  collect        docs/evidence/runs/            docs/facts/*.json         render·check             build
```

- 사실은 기계가: 명령을 셸 없이 실행해 원시 출력과 sha256 을 남기고, 정해진 규칙으로 값을 뽑습니다.
- 문장은 AI 가: 초안에는 숫자 대신 `{{fact:키}}` 자리표시자를 쓰게 합니다.
- 판단은 사람이: `pidoc check` 가 근거 없는 숫자·틀린 인용·낡은 출력·내부 정보를 드러내고, 사람이 고칩니다.

할 수 있는 것과 없는 것: 근거 없는 수치를 상당수 막고 나머지를 검토 대상으로 드러냅니다.
문장의 뜻이 맞는지, 사실을 맞는 자리에 썼는지는 사람이 봐야 합니다.

## 준비

파이썬 3.11 이상. 핵심 기능은 표준 라이브러리만 씁니다.

```sh
git clone <이 저장소> pidoc && cd pidoc
python3 -m venv .venv
.venv/bin/pip install -e .              # pidoc 명령이 생깁니다
.venv/bin/pip install -e '.[pdf]'       # HTML(markdown-it-py)·PDF(WeasyPrint)도 쓰려면
```

설치하지 않고 `PYTHONPATH=<pidoc 폴더> python3 -m pidoc ...` 로 돌려도 됩니다.
PDF 는 시스템에 Pango 가 있어야 하고, 한글 글꼴은 나눔고딕(`NanumGothic`)을 씁니다. **한글 글꼴이 없으면 PDF 는 종료 코드 0 으로 만들어지지만 한글이 네모 상자로 나옵니다** — 만든 뒤 `pdffonts` 로 한글 글꼴이 들어갔는지 보세요.

## 따라 하기: pimon 문서 만들기 (PC 만으로)

### 1. pimon 받기와 설정 복사

```sh
git clone https://github.com/jjoong2dov/pimon.git
cd pimon
cp -r ../pidoc/examples/pimon/docs/. docs/
```

`docs/pidoc.toml` 이 설정, `docs/src/` 가 문서 원본입니다(`quickstart.md`, `reference.md`).

### 2. 수집: 명령을 실행해 증거와 사실 만들기

```sh
pidoc collect --target pc
```

```
[pc] run 20261026T191351-pc
  성공 fake_pi (33 ms, 사실 0개)
  성공 python_version (4 ms, 사실 1개)
  성공 pimon_help (64 ms, 사실 1개)
  성공 pimon_once (65 ms, 사실 3개) (가림 1곳)
  성공 check_config (65 ms, 사실 1개)
[pc] 사실 6개 갱신 → docs/facts/pc.json
```

- 출력이 `max_output` 을 넘어 잘리거나, UTF-8 이 아니거나, 사실 하나라도 못 뽑으면 그 명령은 실패이고 그 명령의 사실은 하나도 갱신하지 않습니다.
- `--token 값`·`--password=값` 같은 argv 의 민감한 값은 증거에 `<가림>` 으로 남습니다.
- 실행 기록은 `docs/evidence/runs/<run-id>/` 에: `manifest.json`, 명령마다 `.stdout`·`.stderr`(원시 바이트)·`.json`(argv, 종료 코드, 걸린 시간, sha256 ...).
- "가림 1곳": pimon 출력의 `"host"` 에 든 이 PC 의 실제 hostname 을 대상 별칭(`devpc`)으로 바꿨다는 뜻입니다.
- `pidoc facts` 로 사실을 봅니다(키·값·타입·나이·출처 run).

### 3. 코드에서 레퍼런스 뽑기

```sh
pidoc extract cli config http py      # → docs/facts/code.json
```

argparse 옵션 도움말, `config.py` 의 기본값 딕셔너리, `pimon.toml.example` 의 값과 주석, HTTP 경로, docstring 을
**실행하지 않고** 읽어 사실로 만듭니다.

### 4. 렌더와 검사

```sh
pidoc render        # docs/src → docs/out
pidoc check         # 문서 시험
pidoc build --pdf   # docs/out/site.html, site.pdf
```

일부러 틀려 보기:

```sh
echo 'pimon 은 5초마다 수집하고 라즈베리파이 에서 돕니다.' >> docs/src/quickstart.md
pidoc check
```

```
docs/src/quickstart.md:36: [numbers] 근거 없는 숫자: 5 — {{fact:키}} 로 바꾸거나 줄 끝에 <!-- pidoc-ok: 이유 --> 를 다세요
docs/src/quickstart.md:36: [terms] '라즈베리파이' 대신 '라즈베리 파이'
문서 2개 검사: 오류 2, 경고 0
```

코드가 바뀌면:

```sh
pidoc stale                 # render 때 남긴 sha256 과 비교
pidoc stale --since HEAD    # git diff 로 (CI 에서 PR 마다)
```

## 문서 원본 문법 (docs/src/*.md)

| 쓰는 법 | 뜻 |
|---|---|
| `<!-- pidoc-target: pc -->` | 첫 줄들(머리말). 대상을 적지 않은 사실 참조의 기본 대상 |
| `<!-- pidoc-deps: pimon/server.py -->` | 이 문서가 기대는 파일(stale 용) |
| `{{fact:키}}`, `{{fact:대상:키}}` | 사실 값. 없거나 만료면 render·check 오류 |
| `{{fact:키\|int}}` `\|round1` `\|join` `\|code` `\|raw` | 정해진 표시 변환만(이어 쓰기 가능). 본문에 넣는 값은 Markdown 특수 문자를 이스케이프하고, `\|raw` 만 그대로 넣습니다 |
| ```` ```console pidoc-run=명령id target=pc ```` | 본문을 비워 두면 render 가 그 명령의 최신 수집 stdout 으로 채움(최신 수집이 실패했으면 오류) |
| ```` ```sh pidoc-ok=이유 ```` | 이 코드 블록의 숫자는 근거가 있다고 표시 |
| ```` ```python pidoc-quote=pimon/config.py#L9-L26 ```` | render 가 파일에서 채움. 본문이 있으면 check 가 파일과 대조 |
| 줄 끝 `<!-- pidoc-ok: 이유 -->` | 그 줄의 숫자를 일부러 허용(이유 필수) |

## 명령

| 명령 | 하는 일 |
|---|---|
| `pidoc init [폴더]` | `docs/` 뼈대와 `pidoc.toml` 견본 |
| `pidoc collect [--target T] [--only ID...] [--keep-raw]` | 실행 → 증거 → 사실. 실패한 명령의 사실은 갱신하지 않고 계속, 끝에 종료 코드 3 |
| `pidoc replay <runs 폴더>` | 저장된 증거에서 사실만 다시 뽑기(파이 없는 독자용) |
| `pidoc facts [--target T] [--json]` | 사실 목록 |
| `pidoc extract cli\|config\|http\|py` | 코드에서 레퍼런스 사실(`facts/code.json`) |
| `pidoc draft <틀.md> --out <파일> [--ai claude\|codex\|none]` | 틀 + 사실 목록으로 AI 초안. 숫자가 들어오면 그 줄을 보여 주고 종료 1 |
| `pidoc render [파일...]` | 사실·인용 채우기, `docs/out/.deps.json` 기록 |
| `pidoc check [파일...] [--only 검사...] [--json] [--rerun]` | 문서 시험 |
| `pidoc stale [--since REV]` | 다시 봐야 할 문서 |
| `pidoc build [--pdf]` | HTML 한 파일 + 선택 PDF |
| `pidoc walk <렌더된 문서> --target T [--from N] [--dry-run]` | 따라 하기 문서의 ```` ```sh pidoc-step ```` 블록을 대상에서 차례로 실행, 실패하면 멈추고 종료 3 |
| `pidoc notes <범위> [--ai ...] [--check 파일]` | git 커밋 → 사실 → 릴리스 노트 초안, 범위 밖 해시 검사 |
| `pidoc report <junit.xml>` | pytest 결과 → 사실 → 시험 보고서 |
| `pidoc i18n-check <원본.md> <번역.md>` | 코드·자리표시자·링크·숫자가 같은지 |

종료 코드: 0 성공, 1 검사 실패(문서 문제), 2 사용법·설정 오류, 3 수집 실패(명령 실패·시간 초과).

## 검사 (pidoc check)

| 검사 | 보는 것 |
|---|---|
| facts | 없는 키, 변환·타입, 만료(`max_age_days`), **증거와 맞는지**(그 run 의 stdout 에서 같은 규칙으로 다시 뽑아 비교, 코드 사실은 원본 파일 sha256, 더 최근 수집이 실패했으면 오류), 쓰이지 않는 사실(경고) |
| numbers | 본문 숫자 리터럴(오류). 머리글 번호, 두 자리까지의 번호 목록, 1부터 느는 표 첫 열, 장·절 참조, `IPv4`·`UTF-8` 같은 이름, 커밋 해시, `number_allow`, `pidoc-ok` 는 뺀다. 코드(펜스·인라인)의 숫자는 `check.code_numbers` 등급(기본 경고). 한글 수사("두 번")·비교 표현("최신", "빠르다")은 경고 |
| quote | pidoc-quote 블록이 실제 파일과 같은지 |
| run | pidoc-run 블록의 증거가 있는지, 본문이 있으면 증거와 같은지(정규화 뒤). `--rerun` 이면 지금 다시 실행해 비교 |
| links | 상대 링크의 파일과 `#앵커` |
| terms | `docs/terms.toml` 용어집(`"바른말" = ["틀린말", ...]`) |
| secrets | IPv4·IPv6·MAC·이메일·실제 hostname·금지어(`docs/banned.txt`, 저장소에 넣지 않음)·개인키·Bearer·흔한 API 토큰·URL 안 비밀번호·홈 폴더 경로. src·out·facts·evidence·ai 모두. **휴리스틱이라 모든 비밀을 찾지는 못합니다** |

## 설정 (docs/pidoc.toml) 요약

모르는 키는 오류입니다(오타를 조용히 넘기지 않습니다). 전체 예는 [examples/pimon/docs/pidoc.toml](examples/pimon/docs/pidoc.toml).

| 표 | 키 |
|---|---|
| `[project]` | `name`, `root`(이 파일 기준 대상 저장소), `default_target` |
| `[targets.이름]` | `kind`(local\|ssh), `host`(ssh, `PIDOC_TARGET_<이름>` 환경변수로 덮어씀), `alias`, `cwd`, `known_hosts`(이 대상만의 호스트 키 파일, docs 기준 경로) |
| `[collect]` | `timeout_s`, `max_output`, `env_allow`, `env_set`, `allow_programs` |
| `[[command]]` | `id`, `argv`, `targets`, `cwd`, `timeout_s`, `ok_exit`, `[[command.fact]]`(`key`, `extract`=stdout_all\|stdout_line\|regex\|json, `pattern`, `line`, `path`, `sep`, `type`=string\|int\|float\|list\|bool, `max_age_days`) |
| `[redact]` | `patterns = [{re, to}]`, `hostname`, `names`, `home`(이 PC 홈 경로 → ~, 기본 켬) — 수집 직후 증거·사실에 적용. ssh 대상의 실제 호스트 이름은 수집 때 `uname -n` 으로 알아내 가린다 |
| `[mask]` | `time`, `hostname`, `pid`, `patterns` — run 비교 때만 |
| `[extract]` | `paths`, `config_example`, `config_module`, `config_defaults` |
| `[check]` | `numbers`·`code_numbers`(error\|warn\|off), `number_allow`, `stale_deps`, `unused_facts`, `terms`, `banned`, `ip_allow`, `email_allow`, `home_allow`(기본 ["pi"]) |
| `[ai]` | `provider`(claude\|codex\|none, 기본 none), `model`, `timeout_s`, `facts`(AI 에 보낼 사실 패턴, 기본 ["*"]) |
| `[walk]` | `timeout_s`(단계마다, 기본 600), `cwd`(시작 폴더, 기본: ssh 는 로그인 홈, 로컬은 프로젝트 루트) |
| `[build]` | `title`, `order` |

## 파이에서 수집 (ssh)

```sh
export PIDOC_TARGET_PI=pi@<파이 주소>     # 설정 파일에 주소를 남기지 않으려면
pidoc collect --target pi
```

- `ssh -o BatchMode=yes -o StrictHostKeyChecking=yes` 로 돌립니다. 비밀번호를 묻지 않고, 처음 보는 호스트 키는 거절합니다.
  먼저 `ssh pi@<주소>` 로 한 번 접속해 호스트 키를 확인·저장하고, 키 로그인을 준비하세요.
- 원격 명령은 `shlex.join` 으로 한 줄이 되어 원격 셸이 해석합니다. 그래서 ssh 대상은 `allow_programs` 가 꼭 있어야 하고,
  목록 밖 프로그램은 실행하지 않습니다.

### allow_programs 는 보안 경계가 아니라 실수 방지 목록입니다

첫 argv 의 이름만 봅니다. `python3` 을 허용하면 python3 이 할 수 있는 일은 무엇이든 할 수 있습니다.
설정 파일을 고칠 수 있는 사람은 무엇이든 실행할 수 있다고 보세요. 목록이 막는 것은 오타와 실수입니다.
그래도 흔한 구멍은 막아 둡니다.

- 셸·실행기(`sh`, `bash`, `env`, `sudo`, `xargs`, `timeout`, `ssh` …)는 목록에 넣을 수 없습니다(설정 오류).
- 인라인 코드 실행(`python3 -c`, `perl -e`, `node -e` …)은 거절합니다. 스크립트 파일로 만들어 저장소에 두세요.
- argv 에 줄바꿈·제어 문자를 쓸 수 없습니다.

정말 격리가 필요하면 수집 전용 계정(권한 없는 사용자)이나 컨테이너에서 돌리세요.
- 파이가 없는 독자는 저장소에 들어 있는 증거로 `pidoc replay docs/evidence/runs` 를 돌리면 같은 사실을 얻습니다.

## 따라 하기 문서 시험 (pidoc walk)

튜토리얼은 독자가 그대로 칠 명령이므로, 문서 자체를 대상에서 실행해 봅니다.

````markdown
```sh pidoc-step
git clone https://github.com/jjoong2dov/pimon.git
cd pimon
```

```sh pidoc-step
python3 -m pimon check-config --config pimon.toml.example
```
````

```sh
pidoc render
pidoc walk docs/out/pi-tutorial.md --target pi --dry-run   # 무엇을 실행할지 보기
pidoc walk docs/out/pi-tutorial.md --target pi             # 실패하면 "N단계 실패" + 마지막 출력, 종료 3
pidoc walk docs/out/pi-tutorial.md --target pi --from 3    # 고친 뒤 이어서
```

- 블록 하나가 한 단계이고 `bash -e -o pipefail -c '<블록>'` 으로 돕니다(ssh 대상은 collect 와 같은 ssh 옵션).
- **이 기능은 셸을 쓰고 `allow_programs` 를 적용하지 않습니다.** 문서에 적힌 명령이 곧 시험 대상이기 때문입니다.
  믿을 수 있는 문서만, 시험용 장비·계정에서 돌리세요.
- 단계 사이에 작업 폴더(`cd`)는 이어지고, 환경변수(`export`)는 이어지지 않습니다.
- 기록은 `docs/evidence/walks/<id>/`(단계마다 스크립트·stdout·stderr·종료 코드·시간, 가리기 적용). 단계 시간 제한은 `[walk] timeout_s`(기본 600초).

## AI 초안

```sh
pidoc draft 틀.md --out docs/src/usage.md --ai claude    # claude -p 에 프롬프트를 stdin 으로
pidoc draft 틀.md --out docs/src/usage.md --ai codex     # codex exec -
pidoc draft 틀.md --out docs/src/usage.md --ai none      # 부르지 않고 프롬프트만 저장
```

호출마다 `docs/ai/<시각>-draft/` 에 `prompt.txt`, `input.sha256`, `meta.json`(도구·argv·모델·시각·종료 코드), `raw.txt`(받은 그대로)가 남습니다.
프롬프트에는 사실 값이 들어가므로 `docs/ai/` 는 기본으로 git 에 넣지 않습니다(`pidoc init` 이 .gitignore 에 넣음).
보낼 사실은 `[ai] facts = ["pc:*", "code:config.*"]` 처럼 줄일 수 있고, 보내기 전에 secrets 검사와 같은 규칙으로
프롬프트를 훑어 걸리면 보내지 않습니다.

## CI 에서 (예: GitHub Actions)

```yaml
- run: pip install -e ./pidoc
- run: pidoc check --only facts numbers quote links terms secrets
- run: pidoc stale --since origin/main
```

## 가지와 태그

| 태그 | 내용 |
|---|---|
| `ch04` | 로컬 수집기: 설정·init·runner·증거·사실·facts |
| `ch05` | ssh 수집·replay·가리기 |
| `ch06` | extract cli·config·http·py |
| `ch07` | AI adapter·draft |
| `ch08` | render·check facts·numbers |
| `ch09` | check quote·run, 정규화 |
| `ch10` | check links·terms·secrets, stale |
| `ch11` | build(HTML·PDF) |
| `ch12` | notes·report·i18n-check |
| `v0.1` | pimon 견본(examples/pimon)·README |
| `v0.2-review1` | Codex 코드 리뷰 1차 반영([REVIEW1.md](REVIEW1.md)) + `pidoc walk`. 13장(파이 실기)의 출발점 |
| `v0.3-pi` | 13장 파이 실기에서 찾아 고친 것: 대상별 `known_hosts`, 이 PC 홈 경로 가리기, walk 시작 폴더, ssh 대상의 실제 호스트 이름 가리기. 예제에 파이 설치 튜토리얼(`examples/pimon/docs/src/pi-install.md`) |
| `v0.4` | 12장 응용 실행에서 고친 것: i18n-check 링크를 문서 위치 기준으로 비교, git 사실의 숫자로만 된 커밋 해시를 숫자 검사에서 뺌 |
| `v0.5` | 원고 작업 중 발견: secrets 가 `.xml`(junit.xml 의 hostname) 등도 검사, `check --rerun` 이 ssh 실패 때 죽던 것, PDF 가 막은 주소를 경고, 한글 글꼴 안내 |
| `v0.6` | Codex 최종 사실 검토에서 고친 것: 코드 사실도 같은 추출기로 다시 뽑아 값을 대조, HTML 에서 하위 폴더 문서의 링크 변환 |

설계와 달라진 점은 [DESIGN_CHANGES.md](DESIGN_CHANGES.md), 작업 규칙은 [CLAUDE.md](CLAUDE.md).

## 시험

```sh
.venv/bin/pip install pytest
.venv/bin/python -m pytest -q
```

ssh·claude·codex 는 가짜 실행 파일을 PATH 앞에 두고 시험합니다. markdown-it-py·WeasyPrint 가 없으면 그 시험은 건너뜁니다.

## 라이선스

MIT. [LICENSE](LICENSE) 를 보십시오.
