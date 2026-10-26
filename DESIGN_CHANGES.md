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
