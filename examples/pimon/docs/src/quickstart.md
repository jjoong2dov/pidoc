<!-- pidoc-target: pc -->
<!-- pidoc-deps: fake/make_fake.py -->
# 빠른 시작 (PC, 가짜 파이)

라즈베리 파이가 없어도 PC 에서 가짜 파이 폴더로 pimon 을 돌려 볼 수 있습니다.
이 문서의 명령과 출력은 {{fact:system.python_version}} 버전의 파이썬에서 실제로 실행한 기록입니다.

## 가짜 파이 만들기

```sh
python3 fake/make_fake.py fake/pi --fresh
```

## 한 번 수집하기

```sh
python3 -m pimon once --root fake/pi --state-dir fake/state
```

실제 출력(host 는 문서용 이름으로 바꿨습니다):

```json pidoc-run=pimon_once
```

가짜 파이의 온도는 {{fact:pimon.fake.temp|round1}}도이고, 판정은 {{fact:pimon.fake.level|code}} 입니다.
유선 링크 속도는 {{fact:pimon.fake.link_speed}} Mb/s 로 나옵니다.

## 설정 파일 검사

```sh
python3 -m pimon check-config --config pimon.toml.example
```

견본 설정이면 이렇게 나옵니다: {{fact:pimon.check_config_message|code}}
쓸 수 있는 하위 명령은 [레퍼런스](reference.md#하위-명령)에 있습니다.
