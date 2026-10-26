# 틀: 새 라즈베리 파이에 pimon 설치하고 처음 돌려 보기

이 틀로 docs/src/pi-install.md 의 원본을 써 줘. 독자는 라즈베리 파이 OS(64비트 Lite)를 막 구운 파이에 ssh 로 들어온 상태다(사용자 pi, 홈 폴더 /home/pi).
pimon 공개 저장소 주소는 https://github.com/jjoong2dov/pimon 이다. 이 저장소(지금 폴더의 상위)의 코드와 README 를 읽고 써도 된다.

꼭 지킬 것:
- 한국어, 따라 하기 문서. 단계마다 짧은 설명 + 파이에서 칠 명령 블록.
- 파이에서 칠 명령 블록은 정보 문자열을 ```sh pidoc-step 으로 쓴다. 한 블록 = 한 단계. 블록 안에는 명령만(출력 넣지 말 것). 블록은 처음부터 끝까지 순서대로 그대로 쳐서 성공해야 한다. 대화형 입력이 필요한 명령은 쓰지 않는다.
- 첫 단계에서 pimon 을 ~/pimon 에 받는다. 마지막 단계는 pimon 이 실제 파이에서 한 번 수집(once)해 판정을 출력하는 것과, systemd 서비스로 띄워 HTTP /status 가 응답하는지 확인하는 것.
- 버전·온도 같은 숫자를 본문에 직접 쓰지 말 것. 아래 사실은 {{fact:pi:키}} 로 참조하고, 없는 값은 쓰지 말 것.
- 명령 출력 예시를 지어내지 말 것. 출력을 보여 주고 싶은 곳에는 빈 블록 ```console pidoc-run=pimon_once_pi target=pi 처럼 자리만 남긴다(지금 쓸 수 있는 run id 는 pimon_once_pi 하나).
