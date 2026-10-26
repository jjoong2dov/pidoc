# pimon 견본

pimon 저장소의 `docs/` 에 복사해 쓰는 pidoc 설정과 문서 원본입니다.

```sh
cp -r examples/pimon/docs/. <pimon 저장소>/docs/
cd <pimon 저장소>
pidoc collect --target pc      # 가짜 파이로 PC 에서
pidoc extract cli config http py
pidoc render && pidoc check
pidoc build --pdf
```

- `docs/pidoc.toml`: 대상 `pc`(로컬)·`pi`(ssh, 주소는 `PIDOC_TARGET_PI`), 명령 7개, 가리기·정규화·검사 설정
- `docs/src/quickstart.md`: 빠른 시작(가짜 파이) — `pidoc-run` 으로 `pimon once` 의 실제 출력을 넣는다
- `docs/src/reference.md`: CLI·설정 레퍼런스 — 코드에서 뽑은 사실과 `pidoc-quote`
- `docs/terms.toml`: 용어집
