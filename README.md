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
PDF 는 시스템에 Pango 가 있어야 하고, 한글 글꼴은 나눔고딕(`NanumGothic`)이 있으면 그것을, 없으면 기본 글꼴을 씁니다.

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
| `{{fact:키\|int}}` `\|round1` `\|join` `\|code` | 정해진 표시 변환만(이어 쓰기 가능) |
| ```` ```console pidoc-run=명령id target=pc ```` | 본문을 비워 두면 render 가 최신 성공 run 의 stdout 으로 채움 |
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
| `pidoc notes <범위> [--ai ...] [--check 파일]` | git 커밋 → 사실 → 릴리스 노트 초안, 범위 밖 해시 검사 |
| `pidoc report <junit.xml>` | pytest 결과 → 사실 → 시험 보고서 |
| `pidoc i18n-check <원본.md> <번역.md>` | 코드·자리표시자·링크·숫자가 같은지 |

종료 코드: 0 성공, 1 검사 실패(문서 문제), 2 사용법·설정 오류, 3 수집 실패(명령 실패·시간 초과).

## 검사 (pidoc check)

| 검사 | 보는 것 |
|---|---|
| facts | 없는 키, 변환·타입, 만료(`max_age_days`), 쓰이지 않는 사실(경고) |
| numbers | 본문 숫자 리터럴. 펜스·인라인 코드, 머리글 번호, 번호 목록, 표 첫 열 순번, 장·절 참조, `IPv4`·`UTF-8` 같은 이름, 커밋 해시, `number_allow`, `pidoc-ok` 는 뺀다. 한글 수사("두 번")·비교 표현("최신", "빠르다")은 경고 |
| quote | pidoc-quote 블록이 실제 파일과 같은지 |
| run | pidoc-run 블록의 증거가 있는지, 본문이 있으면 증거와 같은지(정규화 뒤). `--rerun` 이면 지금 다시 실행해 비교 |
| links | 상대 링크의 파일과 `#앵커` |
| terms | `docs/terms.toml` 용어집(`"바른말" = ["틀린말", ...]`) |
| secrets | IP·이메일·실제 hostname·금지어(`docs/banned.txt`, 저장소에 넣지 않음). src·out·facts·evidence 모두 |

## 설정 (docs/pidoc.toml) 요약

모르는 키는 오류입니다(오타를 조용히 넘기지 않습니다). 전체 예는 [examples/pimon/docs/pidoc.toml](examples/pimon/docs/pidoc.toml).

| 표 | 키 |
|---|---|
| `[project]` | `name`, `root`(이 파일 기준 대상 저장소), `default_target` |
| `[targets.이름]` | `kind`(local\|ssh), `host`(ssh, `PIDOC_TARGET_<이름>` 환경변수로 덮어씀), `alias`, `cwd` |
| `[collect]` | `timeout_s`, `max_output`, `env_allow`, `env_set`, `allow_programs` |
| `[[command]]` | `id`, `argv`, `targets`, `cwd`, `timeout_s`, `ok_exit`, `[[command.fact]]`(`key`, `extract`=stdout_all\|stdout_line\|regex\|json, `pattern`, `line`, `path`, `sep`, `type`=string\|int\|float\|list\|bool, `max_age_days`) |
| `[redact]` | `patterns = [{re, to}]`, `hostname`, `names` — 수집 직후 증거·사실에 적용 |
| `[mask]` | `time`, `hostname`, `pid`, `patterns` — run 비교 때만 |
| `[extract]` | `paths`, `config_example`, `config_module`, `config_defaults` |
| `[check]` | `numbers`(error\|warn\|off), `number_allow`, `stale_deps`, `unused_facts`, `terms`, `banned`, `ip_allow`, `email_allow` |
| `[ai]` | `provider`(claude\|codex\|none, 기본 none), `model`, `timeout_s` |
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
- 파이가 없는 독자는 저장소에 들어 있는 증거로 `pidoc replay docs/evidence/runs` 를 돌리면 같은 사실을 얻습니다.

## AI 초안

```sh
pidoc draft 틀.md --out docs/src/usage.md --ai claude    # claude -p 에 프롬프트를 stdin 으로
pidoc draft 틀.md --out docs/src/usage.md --ai codex     # codex exec -
pidoc draft 틀.md --out docs/src/usage.md --ai none      # 부르지 않고 프롬프트만 저장
```

호출마다 `docs/ai/<시각>-draft/` 에 `prompt.txt`, `input.sha256`, `meta.json`(도구·argv·모델·시각·종료 코드), `raw.txt`(받은 그대로)가 남습니다.

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
| `v0.1` | pimon 견본(examples/pimon)·README. 13장(파이 실기)의 출발점 |

설계와 달라진 점은 [DESIGN_CHANGES.md](DESIGN_CHANGES.md), 작업 규칙은 [CLAUDE.md](CLAUDE.md).

## 시험

```sh
.venv/bin/pip install pytest
.venv/bin/python -m pytest -q
```

ssh·claude·codex 는 가짜 실행 파일을 PATH 앞에 두고 시험합니다. markdown-it-py·WeasyPrint 가 없으면 그 시험은 건너뜁니다.

## 라이선스

MIT. [LICENSE](LICENSE) 를 보십시오.
