# Codex 코드 리뷰 1차 반영 기록

- 리뷰: `evidence/cx_plan/lab_r1.txt`(책 작업 폴더). Codex 가 읽기 전용으로 `v0.1` 을 검토했다.
- 방법: 지적마다 먼저 **재현 시험**을 `tests/test_review1.py` 에 쓰고, 고치기 전 코드에서 돌려 실패하는 것을 확인했다
  (33개 중 32개 실패, 통과한 1개 `test_r07_generated_and_ok_blocks_skip` 은 고친 뒤에도 지켜야 할 예외를 고정하는 시험).
  그다음 고쳐서 모두 통과시켰다.
- 커밋: `6160ba1`(지적 1~18 반영), `cc86345`(walk 와 문서). 태그 `v0.2-review1`.
- 번호는 리뷰 본문의 번호다. 리뷰 끝의 "출간 전에 꼭 고칠 것" 12개는 본문 1·2·3·4·5·6·7·8·9·10·13·14번에 해당한다.

| 번호 | 지적 | 재현 여부(어떻게) | 조치(커밋) | 시험 이름 |
|---|---|---|---|---|
| 1 | facts 파일을 손으로 고쳐도 출판됨 | 재현. collect 뒤 pc.json 의 value 만 바꿨는데 check·render 가 통과(종료 0). code 사실도 원본 파일을 바꿔도 통과 | `verify.py` 를 새로 둠. render·check 가 쓰기 전에 run 의 stdout sha256, 같은 규칙으로 다시 뽑은 값·타입, 원본 파일 sha256 을 확인. git·test 사실은 원본을 남기지 않아 확인 범위 밖(README·코드 주석에 적음) (6160ba1) | test_r01_hand_edited_fact_is_rejected, test_r01_code_fact_source_changed |
| 2 | pidoc-quote 가 저장소 밖 파일을 복사 | 재현. `pidoc-quote=/etc/hosts`, `../secret.txt`, 밖을 가리키는 심볼릭 링크 셋 다 렌더됨. pidoc-deps 의 `../../../etc/passwd` 도 "파일이 없습니다"로만 처리됨 | `Config.inside()`(resolve 뒤 root 안인지)를 quote·deps·stale_deps·extract 경로·로컬 cwd 에 적용 (6160ba1) | test_r02_quote_outside_root, test_r02_deps_outside_root |
| 3 | 사실·출력이 Markdown 구조를 탈출 | 재현. 출력에 ```` ``` ```` 가 있는 pidoc-run 블록이 원래 펜스를 닫고 그 뒤 `![x](file:///etc/passwd)` 가 본문이 됨. 여러 줄 사실이 본문에 그대로 들어감. 사실 값 이스케이프 시험은 고치기 전 `\|raw` 가 없어 먼저 실패했고, 이스케이프가 없다는 것은 코드로 확인 | 본문 사실은 `\ ` * _ [ ] < > \| !` 를 이스케이프하고, 그대로 넣는 `\|raw` 를 더함. `\|code` 는 값보다 긴 백틱을 씀. 펜스 안에서는 ```` ``` ````·`~~~` 가 든 값을 거절. 여러 줄 사실은 본문에 넣지 못하게 함. quote·run 블록 펜스는 본문보다 길게. PDF 는 data: 와 저장소 안 file: 만 가져옴(PDF 쪽은 고친 뒤 시험을 더함) (6160ba1) | test_r03_fact_is_escaped, test_r03_multiline_fact_in_prose_is_error, test_r03_run_output_cannot_close_fence, test_r03_pdf_fetcher_blocks_outside |
| 4 | 잘린 출력을 정상 사실로 인정 | 재현. `max_output=4`, 출력 `123456789` 에서 collect 가 종료 0, int 사실 생성 | 잘리면(stdout·stderr 모두) 그 명령은 실패이고 사실은 갱신하지 않음. 저장하는 출력은 마지막 줄바꿈까지만 남겨 끝나지 않은 줄(비밀 조각)을 버림. replay 도 잘린 기록은 건너뜀 (6160ba1) | test_r04_truncated_output_is_failure |
| 5 | 한 명령에서 추출 일부만 실패해도 나머지는 갱신 | 재현. 규칙 둘 중 하나가 실패해도 x.a 가 새 값(5)으로 바뀜 | 명령 단위로 원자적: 추출 오류가 하나라도 있으면 그 명령의 사실은 하나도 갱신하지 않음. replay 도 같음 (6160ba1) | test_r05_partial_extraction_updates_nothing |
| 6 | stale 이 사실·run 변경을 못 봄 | 재현. 같은 키를 새 값으로 다시 collect 해도 "낡은 문서 없음" | .deps.json 에 사실 해시(값·타입·run·source_sha256), run 이름·stdout sha256 을 남기고 stale 이 비교함 (6160ba1) | test_r06_stale_sees_fact_and_run_change |
| 7 | 코드 펜스·인라인 코드가 숫자 검사를 통째로 우회 | 재현. 펜스 안과 인라인 코드의 `Python 99.7 … 65535` 가 둘 다 결과 없음 | 코드 안 숫자도 검사함. 오탐이 폭발하지 않도록 등급은 `check.code_numbers`(기본 warn)로 따로 두고, 근거는 펜스 `pidoc-ok=이유` 나 줄 끝 `<!-- pidoc-ok: 이유 -->` 로 표시. pidoc-run·pidoc-quote 블록은 render 가 증거·파일에서 채우므로 세지 않음. examples/pimon 은 오류 0·경고 0 그대로 (6160ba1) | test_r07_numbers_in_code_are_warned, test_r07_generated_and_ok_blocks_skip, test_numbers.py::test_scan_code_warns_and_ok_comments |
| 8 | 렌더가 실패해도 옛 결과가 남음 | 재현. 정상 렌더 뒤 없는 사실을 넣고 다시 렌더하면 종료 1인데 옛 docs/out/use.md 가 그대로 | 실패한 문서는 이전 결과와 .deps.json 기록을 지우고 그 사실을 알림. build 가 실패하면 이전 site.html·pdf 도 지움 (6160ba1) | test_r08_old_output_removed_on_failure |
| 9 | AI 기록에 비밀이 남는데 검사·gitignore 대상이 아님 | 재현. docs/ai 안의 사설 IP 를 secrets 가 못 봄. init 의 .gitignore 에 ai/ 가 없음. 보낼 사실을 고를 방법이 없음(`[ai] facts` 가 설정 오류) | `[ai] facts` 패턴으로 보낼 사실을 고름(기본 전부). 보내기 전에 secrets 규칙으로 프롬프트를 검사해 걸리면 보내지도 저장하지도 않음(종료 2). secrets 가 docs/ai 를 봄. init 이 ai/ 를 gitignore 함 (6160ba1) | test_r09_ai_prompt_secret_scan_and_allowlist, test_r09_secrets_scans_ai_dir_and_gitignore |
| 10 | allow_programs 는 보안 경계가 아님 | 재현. `bash` 를 목록에 넣을 수 있고, `python3 -c ...` 가 통과함 | README·`collect --help`·코드 주석에 "보안 경계가 아니라 실수 방지 목록"이라고 씀. 강화한 것: 셸·실행기(sh, bash, env, sudo, xargs, timeout, ssh …)는 목록에 넣으면 설정 오류, 인라인 코드 실행(python -c, perl -e, node -e …)은 거절, argv 의 줄바꿈·제어 문자 금지. 명령별 고정 argv 스키마나 실행 파일 해시 같은 진짜 격리는 하지 않음(README 에서 별도 계정·컨테이너를 권함) (6160ba1) | test_r10_shells_cannot_be_allowed, test_r10_inline_code_flag_refused, test_r10_readme_says_not_a_security_boundary |
| 11 | 비밀 검사 범위가 좁음 | 재현. Bearer 토큰, PEM 개인키 머리, IPv6, URL 안 비밀번호, 홈 폴더 경로, ghp_ 토큰이 모두 통과. argv 의 `--token 값` 이 증거와 manifest 에 그대로 남음 | IPv6(2001:db8::/32 제외)·MAC·개인키·Bearer·API 토큰 모양·URL 사용자:비밀번호·홈 폴더(`home_allow`, 기본 pi) 패턴을 더함. 증거·manifest 의 argv 에서 민감한 옵션 값은 `<가림>`. README 에 "휴리스틱"이라고 씀 (6160ba1) | test_r11_more_secret_patterns, test_r11_sensitive_argv_masked |
| 12 | 이미 있는 .gitignore 면 private 원본이 보호되지 않음 | 재현. `out/` 만 있는 docs/.gitignore 에서 init 해도 evidence/private/ 가 더해지지 않음 | init 이 빠진 줄만 덧붙임(덮어쓰지 않음). `--keep-raw` 는 `git check-ignore` 로 확인해 무시되지 않으면 경고 (6160ba1) | test_r12_existing_gitignore_gets_required_lines |
| 13 | 최신 수집이 실패해도 옛 사실·옛 성공 run 이 유효 | 재현. 성공 뒤 같은 명령이 실패해도 render 가 옛 값과 옛 출력으로 통과 | 그 명령의 가장 최근 시도가 실패면 사실·pidoc-run 둘 다 오류. 최근 성공 run 이 그 사실을 만들지 않았어도 오류. `max_age_days` 기본값은 여전히 없음(사실마다 다르므로 설정에 맡김) (6160ba1) | test_r13_newer_failure_blocks_old_fact |
| 14 | UTF-8 오류를 조용히 � 로 바꿈 | 재현. `v=\377` 출력에서 collect 가 종료 0, 사실은 `v=�` | 사실 추출과 pidoc-run 렌더는 엄격한 UTF-8 로 읽고, 실패하면 그 명령의 실패로 처리. 가리기는 surrogateescape 로 바이트를 보존(그대로). 인코딩 설정 항목은 만들지 않음 (6160ba1) | test_r14_invalid_utf8_is_failure |
| 15 | 영문에 붙은 버전 숫자 누락, 표·목록 순번 오인 | 재현. `Python3.99`·`OpenSSL3.7`·`version3.2`·`2026. 출시` 가 숫자 없음. 순번이 아닌 표 첫 열 `70` 도 빠짐 | 점이 있는 수는 영문에 붙어 있어도 셈(IPv4·x86_64 같은 정수 이름은 계속 뺌). 번호 목록·제목 번호는 두 자리까지만 구조로 봄. 표 첫 열은 1(또는 0)부터 1씩 늘 때만 순번. **고치지 않은 것:** '3장' 예외는 그대로 둠. "3장을 보세요"가 책·문서에서 훨씬 흔해서, '종이 3장' 미탐은 감수하고 주석에 적어 둠 (6160ba1) | test_r15_numbers_attached_to_words, test_r15_table_first_column_must_be_sequence, test_numbers.py::test_table_only_first_column |
| 16 | 출력 경로·로컬 cwd 가 저장소 밖을 허용 | 재현. `draft --out <저장소 밖>` 이 써짐. command `cwd = "../.."` 가 통과 | draft·notes·report 의 `--out` 과 로컬 cwd 를 저장소 안으로 제한(밖이면 종료 2). **부분 수용:** 리뷰가 제안한 `--allow-outside-root` 는 만들지 않음(필요한 경우를 아직 못 봄). docs/src·docs/out 처럼 더 좁게 묶지도 않음(draft 는 틀을 다른 폴더에 둘 수 있게) (6160ba1) | test_r16_draft_out_outside_root, test_r16_command_cwd_outside_root |
| 17 | 사실 타입·JSON 형식 검증이 약함 | 재현. type 을 int 로 바꾼 string 사실이 그대로 읽힘. `float("nan")` 변환이 통과 | 사실 파일을 읽을 때 필수 필드, type 과 실제 값, 유한한 float, 오프셋 있는 시각을 검사(종료 2). float 변환은 nan·inf 를 거절 (6160ba1) | test_r17_fact_file_schema, test_r17_nan_rejected |
| 18 | extract 가 무관한 AST 호출까지 사실로 만듦 | 재현. 다른 객체의 `builder.add_argument("--internal")` 이 옵션에 들어가고, `filesystem_path == "/tmp"` 가 HTTP 경로가 됨 | cli 는 ArgumentParser 를 받은 변수와 그 add_subparsers·add_parser 의 호출만 따라감(하위 명령 옵션은 `cli.<prog>.command.<이름>.option.*`). http 는 self.path 와 거기서 나온 변수와의 비교만 봄 (6160ba1) | test_r18_extract_tracks_receivers |
| P1 | config 검증이 setdefault 로 원본 dict 를 바꿈 | 해당 없음(설계 의견) | **고치지 않음.** 기본값을 채운 명령 정의를 manifest 에 그대로 남기는 것이 의도이고(증거에 "실제로 적용된 규칙"이 남음), 검증·정규화를 한 번에 하는 편이 독자가 따라가기 쉽다고 판단. 이 의도를 REVIEW 에 적음 | — |
| P2 | 부분 Markdown 파서가 여러 모듈에 중복 | 확인(코드 읽기) | **부분 수용.** numbers 가 checks/text.py 의 인라인 코드·주석 정규식을 함께 쓰게 함. 하나의 토큰화 층(CommonMark)으로 모으는 것은 하지 않음. 핵심 기능을 표준 라이브러리만으로 돌리는 원칙 때문(markdown-it-py 는 선택 의존) (6160ba1) | (기존 시험 전부) |
| P3 | 손으로 만든 속성 묶음 클래스 | 해당 없음(설계 의견) | **부분 수용.** Target·Finding 을 dataclass 로 바꿈. Result·Fence·Ref 등은 그대로 둠 (6160ba1) | (기존 시험 전부) |
| P4 | collect.py 의 쓰지 않는 `res` | 확인 | 지움 (6160ba1) | — |
| P5 | Result.argv 의 뜻이 중간에 바뀜 | 확인 | **부분 수용.** `public_argv()`·`public_command()` 로 공개용 argv 를 만드는 곳을 한 군데로 모으고, execute 독스트링에 "result.argv 는 공개용"이라고 적음. 필드를 둘로 나누지는 않음 (6160ba1) | test_r11_sensitive_argv_masked |
| P6 | extract.py 한 파일에 추출기 넷 | 해당 없음(설계 의견) | **고치지 않음.** 6장이 한 파일(약 300줄)을 따라 읽는 구성이라 그대로 둠 | — |

## 요약
- 지적 18개 모두 재현했다(3번의 PDF 주소 부분과 일부 이스케이프는 코드 읽기로 확인).
- 18개 모두 고쳤다. 그중 15·16번은 일부만 받아들였다(이유는 표에).
- 실습 코드 의견 6개(P1~P6)는 고침 1, 부분 수용 3, 고치지 않음 2.
- 같은 판에서 새 기능 `pidoc walk` 를 더했다(cc86345, tests/test_walk.py 6개).
