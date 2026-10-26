# pidoc 작업 규칙 (Claude Code·Codex 용)

## 무엇
실행 증거 없이는 명령·출력·버전·수치가 문서에 들어가지 않게 하는 작은 파이썬 CLI.
흐름: evidence(손대지 않은 실행 기록) → facts(추출 규칙이 기록된 타입 있는 값) → docs/src(사실 키 참조) → docs/out(결과).

## 모듈 지도
- `cli.py` 명령줄 → 각 모듈. `config.py` 설정 읽기·검사(모든 표의 허용 키가 여기).
- 수집: `runner.py`(명령 하나, 셸 없이) · `collect.py`(collect·replay, ssh argv) · `evidence.py`(run 폴더) · `facts.py`(추출·타입·사실 파일) · `redact.py`(공개용 가리기)
- 문서: `doc.py`(머리말·펜스·참조 파싱) · `render.py` · `mask.py`(비교용 정규화) · `checks/*.py`(검사 하나에 모듈 하나, `run(ctx)`) · `stale.py` · `build.py`
- 응용: `extract.py` · `ai.py`·`draft.py` · `notes.py` · `report.py` · `i18n.py`
- 견본: `examples/pimon/docs/`(pimon 저장소의 docs/ 에 복사해 쓰는 설정·문서)

## 규칙
- 핵심은 파이썬 3.11+ 표준 라이브러리만. markdown-it-py(HTML)·WeasyPrint(PDF)는 선택 기능이고, 없으면 그 명령만 친절한 오류.
- 셸 금지: subprocess 에 argv 배열만, shell=True 쓰지 않는다. 원격은 ssh + shlex.join 한 줄 + allow_programs.
- 결정적 출력: JSON 은 `util.dumps`(sort_keys·indent=2·끝 개행). 시각은 `util.now()`(시험은 PIDOC_NOW).
- 종료 코드: 0 성공, 1 검사 실패, 2 사용법·설정 오류(PidocError), 3 수집 실패.
- 메시지·도움말·주석은 한국어로 짧고 친절하게. 과한 추상화 금지(클래스보다 함수).
- 모르는 설정 키는 오류로 멈춘다(오타를 조용히 넘기지 않는다).
- 코드·시험·예제에 회사 이름, 실제 hostname, 사내 IP, 개인 홈 경로를 넣지 않는다. 예시 IP 는 192.0.2.x(문서용 주소).
- 설계(../lab_DESIGN.md)와 다르게 하면 DESIGN_CHANGES.md 에 이유를 적는다.

## 시험
```sh
python -m pytest -q
```
- 외부 프로그램(ssh, claude, codex)은 tests/conftest.py 의 `make_exe` 로 가짜를 PATH 앞에 둔다.
- 표준 라이브러리 밖 의존은 `pytest.importorskip`.
- 오탐을 줄이는 예외(숫자 검사 등)를 고치면 시험으로 고정한다.

## 커밋
장 단위로 시험 통과 → 커밋 → 태그(ch04 … ch12, v0.1).
작성자: `git -c user.name=jjoong2dov -c user.email=jjoong2dov@users.noreply.github.com commit ...`
