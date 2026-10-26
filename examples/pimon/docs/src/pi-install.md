<!-- pidoc-target: pi -->
# 새 라즈베리 파이에 pimon 설치하고 처음 돌려 보기

라즈베리 파이 OS Lite 를 새로 구운 파이에 pimon 을 설치합니다. 파이에서 한 번 수집해 보고, systemd 서비스로 띄워 HTTP 로 응답하는지까지 확인합니다.
사용자 `pi` 로 ssh 접속해 홈 폴더(`/home/pi`)에 있다고 가정합니다.

이 문서의 명령은 다음 파이에서 실제로 실행했습니다.

- 보드: {{fact:pi:system.board_model}}
- OS: {{fact:pi:system.os_name}}
- 커널: {{fact:pi:system.kernel_release}}
- 파이썬: {{fact:pi:system.python_version}}

## pimon 받기

Lite 판에는 git 이 없을 수 있습니다. 그래서 먼저 git 을 설치한 뒤 공개 저장소를 `~/pimon` 에 받습니다.
`-y` 옵션을 붙였으므로 설치 도중에 묻는 것은 없습니다.

```sh pidoc-step
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/jjoong2dov/pimon ~/pimon
```

## 파이썬 확인하기

pimon 은 파이썬 표준 라이브러리만 씁니다. 따라서 파이에 따로 설치할 패키지가 없습니다.
설정 파일(TOML)은 표준 라이브러리의 `tomllib` 로 읽습니다. 아래 `import tomllib` 명령이 오류 없이 끝나면 이 파이의 파이썬으로 pimon 을 돌릴 수 있습니다.

```sh pidoc-step
python3 --version
python3 -c 'import tomllib'
```

<!-- TODO: pimon 이 요구하는 최소 파이썬 버전(사실 목록에 없음) -->

## 설정 견본 검사하기

저장소에 들어 있는 설정 견본 `pimon.toml.example` 을 pimon 이 문제없이 읽는지 검사합니다.
문제가 없으면 {{fact:pc:pimon.check_config_message}} 라고 출력됩니다.

```sh pidoc-step
cd ~/pimon
python3 -m pimon check-config --config pimon.toml.example
```

## 파이에서 한 번 수집하기

이제 실제 파이의 상태를 한 번 읽고 판정합니다. 설정 파일을 주지 않았으므로 기본값으로 돌고, 이때 `root` 는 {{fact:code:config.root.default}} 입니다.
판정은 ok(정상)·warn(주의)·crit(경고)·unknown(모름) 가운데 하나입니다. 결과는 JSON 의 `level` 에 나오고, 항목별 판정은 `checks` 에 나옵니다.

`pimon once` 는 판정이 ok 가 아니면 실패 종료 코드로 끝납니다. 상태를 종료 코드로 알리는 것이므로, 아래 블록에서는 판정과 상관없이 다음 단계로 넘어가도록 `|| true` 를 붙였습니다.

```sh pidoc-step
cd ~/pimon
python3 -m pimon once || true
```

실제 파이에서 나온 출력입니다.

```console pidoc-run=pimon_once_pi target=pi
```

## systemd 서비스로 띄우기

서비스 파일 `deploy/pimon.service` 에는 `ProtectHome=yes` 가 켜져 있습니다. 그래서 서비스는 홈 폴더 아래의 `~/pimon` 을 읽지 못합니다.
이 때문에 코드를 `/opt/pimon` 아래로 복사해서 씁니다. 폴더 배치는 `deploy/deploy.sh` 와 똑같이 맞춥니다. 판마다 `releases/<시각>` 폴더를 만들고, `current` 링크가 지금 쓰는 판을 가리키게 합니다. 이렇게 맞춰 두면 나중에 PC 에서 배포 스크립트로 새 판을 올릴 때도 이 배치를 그대로 이어서 씁니다.

```sh pidoc-step
REL=/opt/pimon/releases/$(date +%Y%m%d-%H%M%S)
sudo mkdir -p "$REL" /etc/pimon
sudo cp -r ~/pimon/pimon ~/pimon/deploy ~/pimon/pimon.toml.example "$REL"/
sudo ln -sfn "$REL" /opt/pimon/current
```

설정 견본을 `/etc/pimon/pimon.toml` 로 복사합니다. 이미 설정 파일이 있으면 덮어쓰지 않습니다. 복사한 다음 서비스가 쓸 코드로 다시 검사합니다.

견본의 `listen` 은 {{fact:code:config.listen.example}} 이므로 같은 네트워크의 다른 컴퓨터에서도 접속할 수 있습니다. 견본에 붙은 주석에도 "{{fact:code:config.listen.comment}}" 라고 적혀 있습니다. 파이 안에서만 보려면 이 단계를 마친 뒤 `listen` 을 기본값 {{fact:code:config.listen.default}} 로 바꾸십시오.

```sh pidoc-step
[ -f /etc/pimon/pimon.toml ] || sudo cp /opt/pimon/current/pimon.toml.example /etc/pimon/pimon.toml
cd /opt/pimon/current
python3 -m pimon check-config --config /etc/pimon/pimon.toml
```

서비스 파일을 설치하고 서비스를 켭니다. `enable --now` 로 켰으므로 지금 바로 시작하고, 재부팅한 뒤에도 저절로 뜹니다.
판정이 ok 이면 보드의 ACT LED 는 원래 동작(SD 카드 접근 표시) 그대로이고, ok 가 아니면 깜빡임으로 알립니다. 서비스를 멈추면 LED 는 원래 동작으로 돌아갑니다.

```sh pidoc-step
sudo cp /opt/pimon/current/deploy/pimon.service /etc/systemd/system/pimon.service
sudo systemctl daemon-reload
sudo systemctl enable --now pimon
```

서비스가 `active (running)` 상태인지 확인합니다. 시작 직후에는 곧 죽을 서비스도 잠깐 running 으로 보이므로 몇 초 기다린 뒤 봅니다.

```sh pidoc-step pidoc-ok=기다리는-초
sleep 3
systemctl is-active pimon
systemctl status pimon --no-pager
```

## HTTP /status 응답 확인하기

`pimon health` 는 설정 파일의 `listen` 주소로 돌고 있는 pimon 의 `/status` 에 요청을 보냅니다. 응답이 오면 호스트 이름과 판정을 한 줄로 출력하고, 응답이 없으면 실패로 끝납니다.
`listen` 이 모든 주소로 열려 있어도 이 명령은 파이 자신에게 묻습니다.

```sh pidoc-step
cd /opt/pimon/current
python3 -m pimon health --config /etc/pimon/pimon.toml
```

같은 서버의 `/` 에서는 웹 화면을, `/metrics` 에서는 Prometheus 텍스트를 볼 수 있습니다.

<!-- TODO: /status 를 curl 로 직접 받아 보는 예시에 쓸 포트 번호(사실 목록에는 listen 주소 문자열만 있음) -->
