# 설계서(lab_DESIGN.md)와 달라진 점

구현하며 설계와 다르게 한 것과 그 이유.

## 모듈
- `util.py`(오류·시각·JSON·해시), `init.py`, `collect.py`(collect·replay 흐름), `redact.py` 를 더했다.
  runner 는 "명령 하나 실행"만, collect 는 "대상·명령 순회와 저장"만 하게 나눠야 시험이 쉽다.

## 수집
- 명령마다 `ok_exit`(기본 [0])를 더했다. pimon `once` 처럼 상태를 종료 코드로 알리는 명령(1=주의)은
  정상 출력인데도 0 이 아니어서, 이것 없이는 수집 실패(3)가 된다.
- 명령마다 `cwd`(대상 저장소 루트 기준, 기본 ".")를 더했고 대상에도 `cwd` 를 둘 수 있다.
  ssh 대상은 원격에서 `cd <폴더> && ...` 로 붙인다.
- `<cmd>.json` 의 argv·cwd 는 실제 실행한 ssh argv·절대 경로가 아니라 **설정의 argv 와 상대 cwd** 를 남긴다.
  ssh argv 에는 비공개 host 가, 절대 경로에는 개인 홈 폴더가 들어가 공개 증거로 새기 때문이다.
  대신 `transport`(local|ssh)와 `redacted`(가린 곳 수)를 더 남긴다.
- `allow_programs`: 로컬은 목록이 비면 검사하지 않고, ssh 는 목록이 꼭 있어야 한다(원격 셸이 줄을 해석하므로).
  허용 목록에 없는 명령은 실행하지 않고 그 명령만 실패(3)로 기록한다.
- ssh argv 에 `-o ConnectTimeout=10` 과 `--`(호스트 앞)를 더했다. env_set 은 원격에서 `env K=V 프로그램 ...` 로 넘긴다.
  ssh 프로세스에는 `SSH_AUTH_SOCK` 이 있으면 넘긴다(ssh-agent).
- `[redact] names = [...]` 로 더 가릴 이름을 줄 수 있다. 로컬 대상의 hostname 은 이 PC 의 hostname,
  ssh 대상은 host 에 적은 이름(과 첫 마디)이다. 다른 낱말의 일부(pi4 와 pi42)는 바꾸지 않는다.
- replay 는 지금 설정의 추출 규칙을 쓰고, 설정에 없는 명령이면 manifest 사본을 쓴다.
  저장된 stdout 의 sha256 이 기록과 다르면 멈춘다(종료 3).

## extract
- 설정 `[extract]`: `paths`(읽을 파이썬 폴더), `config_example`, `config_module`, `config_defaults`(기본 "DEFAULTS").
- 사실 키: `cli.<prog>.{description,commands,options}`, `cli.<prog>.option.<이름>.{help,default,choices}`,
  `config.<점.키>.{default,example,comment}`, `config.keys`, `http.<메서드>.paths`, `py.<모듈>[.<이름>].doc`.
  코드 사실에는 `source`(파일)를 더 남긴다.
- 같은 종류를 다시 뽑으면 그 종류의 옛 키를 지운다(코드에서 사라진 옵션이 사실로 남지 않게).
- `tests` 폴더 안의 파이썬은 읽지 않는다.

## AI 초안
- 설정 `[ai]`: `provider`(claude|codex|none, 기본 none), `model`(claude 는 `--model`, codex 는 `-m`), `timeout_s`(기본 600).
  기본이 none 이라 설정 없이 돌리면 AI 를 부르지 않는다(실수로 비용·외부 전송이 생기지 않게).
- AI 프로세스는 대상 저장소 루트에서 돌린다. 환경변수는 거르지 않는다(로그인 정보가 필요).
- AI 실패(없음·시간 초과·0 아닌 종료)는 종료 코드 3. 기록 폴더 이름은 `<시각>-<용도>`.
- 응답 전체가 ```` ```markdown ```` 로 싸여 오면 벗긴다.

## render·numbers
- `doc.py` 를 더했다: 머리말·펜스·사실 참조·제목 앵커를 줄 단위로 읽는다(render 와 검사들이 같이 씀).
- 사실 참조는 펜스 코드 블록 안에서도 채운다(명령 예시에 버전·포트가 들어가므로). pidoc-quote/run 블록 본문은 빼고.
- `|int` 는 반올림한 정수. 변환은 이어 쓸 수 있다(`|round1|code`).
- 렌더에 오류가 있는 문서는 결과를 쓰지 않는다(반쯤 채운 문서가 docs/out 에 남지 않게).
- .deps.json 은 docs/src 기준 상대 경로를 키로, 의존 파일(머리말 deps + check.stale_deps + 인용 파일)의 sha256,
  쓴 사실(`대상:키`), 쓴 run, 결과 경로, 렌더 시각을 남긴다.
- 숫자 검사 예외를 더했다(시험 tests/test_numbers.py 로 고정):
  - 본문의 장·절 참조(`12장`, `2.1절`). 머리글 번호만 빼면 "3장을 보세요"가 모두 걸렸다.
  - 영문 낱말에 붙은 숫자(IPv4, x86_64, ch04)와 '글자-숫자'(UTF-8, SHA-256). 단 `v1.2` 는 버전이라 센다.
  - 참조식 링크 정의 줄(`[x]: url`)과 `<https://...>`.
- 한글 수사·비교 표현 경고에서 **제목 줄은 뺀다**. 시험 중 `# 빠른 시작` 제목이 '빠른' 경고로 걸린 실제 오탐.
- 한글 수사에서 "한 번"은 세지 않는다("한 번 실행해 보세요" 같은 관용구가 대부분).
- `<!-- pidoc-ok: -->` 처럼 이유가 빈 예외는 오류다.
- 결과 줄에 줄 번호가 없을 때(사실 파일 단위 경고)는 `파일: [검사] ...` 로 쓴다.
- `check.unused_facts`(warn|off). code·git·test 대상의 자동 사실은 '쓰이지 않음' 경고에서 뺀다(수가 많아 소음).

## quote·run
- 정규화는 `mask.py` 에 두었다. 설정 `[mask]`: `time`·`hostname`·`pid`(기본 모두 true), `patterns`(그 밖의 값).
  hostname 정규화는 대상 alias 와 실제 이름을 모두 `<host>` 로 바꾼다(가린 증거와 지금 실행한 출력을 비교하려고).
  정규화는 비교에만 쓰고 문서에 나가는 출력은 바꾸지 않는다.
- run 검사: 블록 본문이 있으면 최신 증거(또는 `--rerun` 이면 지금 실행한 출력)와 비교,
  본문이 없으면 `--rerun` 때 최신 증거와 지금 출력을 비교한다(증거가 낡았는지). `--rerun` 은 증거를 저장하지 않는다.

## links·terms·secrets·stale
- 설정 `[check]` 에 `terms`(기본 terms.toml), `banned`(기본 banned.txt, 둘 다 docs/ 기준), `ip_allow`(주소·CIDR),
  `email_allow`(도메인)를 더했다.
- terms: 영문은 낱말 단위·대소문자 구분. 바른말 안에 든 틀린말(예: '라즈베리 파이4' 안의 '라즈베리 파이')은 바른말을 먼저 지우고 찾는다.
- secrets 는 docs/src·docs/out 에 더해 **docs/facts 와 docs/evidence/runs 도** 본다(전부 파일을 고르지 않았을 때).
  저장소에 같이 공개되는 파일이라서다. 문서용 주소(192.0.2.0/24 등)·루프백·0.0.0.0, example.com 계열은 넘긴다.
  찾은 값은 앞 두 글자만 보여 준다(CI 기록에 다시 새지 않게). 255 를 넘는 마디가 있으면 IP 로 보지 않는다.
- stale: 기본은 .deps.json 의 sha256 비교(+ 원본 문서 자체가 렌더 뒤에 바뀌었는지, render 가 `src_sha256` 를 남김),
  렌더 기록이 없는 문서도 알린다. `--since REV` 는 `git diff --name-only REV --`(작업 트리 포함)로 판단한다.

## build
- 결과는 `docs/out/site.html`(과 `site.pdf`). 설정 `[build]`: `title`, `order`(docs/src 기준 문서 순서).
- 한 파일에 여러 문서를 넣으므로 제목 id 를 `<문서>--<제목 앵커>` 로 하고, 문서 사이 링크(`b.md#x`)를 `#b--x` 로 바꾼다.
  markdown-it 이 링크 주소의 한글을 %인코딩하므로 되돌린 뒤 바꾼다.
- `--pdf` 는 WeasyPrint 가 없으면 **렌더 전에** 멈춘다(반만 만든 결과가 남지 않게). 렌더가 실패하면 HTML 도 만들지 않는다.

## notes·report·i18n
- notes: 사실은 `git.range`·`git.count`·`git.commits`("짧은해시 제목" 목록)·`git.hashes`. 범위가 바뀌면 git.json 을 통째로 바꾼다.
  `--check 파일` 로 AI 없이 해시 검사만 할 수 있다. 숫자가 하나도 없는 16진 낱말(facade 등)은 해시로 보지 않는다.
  초안에는 숫자 검사도 한다.
- 숫자 검사에 예외 하나 더: **커밋 해시처럼 보이는 7~40자 16진 낱말**(a-f 글자와 숫자가 섞인 것).
  notes 시험에서 맞는 해시 `851883f` 의 앞 숫자가 '근거 없는 숫자'로 걸린 실제 오탐. 해시가 맞는지는 notes 가 본다.
- report: 사실은 `test.{tests,passed,failures,errors,skipped,time,failed_cases,source}`. 틀은 render 와 같은 문법,
  기본 결과는 docs/out/test-report.md. 빈 목록의 `|join`(과 표시)은 "(없음)".
- i18n-check: 코드 블록(언어·본문), 인라인 코드, `{{...}}`, 링크 주소, 본문 숫자를 비교한다.
  한국어 '3장'이 숫자 검사에서 빠지므로 영어 쪽 'Chapter 3'·'Section 2.1' 도 뺀다. 설정 파일 없이 돈다.
