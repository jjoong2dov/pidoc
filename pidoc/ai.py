"""AI 호출 adapter. 무엇을 보냈고 무엇을 받았는지 docs/ai/<id>/ 에 남긴다.

  claude  `claude -p` 에 프롬프트를 stdin 으로
  codex   `codex exec -` 에 프롬프트를 stdin 으로
  none    호출하지 않고 프롬프트만 저장(오프라인, 다른 도구에 붙여 넣기용)

기록: prompt.txt, input.sha256, meta.json(도구·argv·모델·시각·종료 코드), raw.txt(받은 그대로)
기록에는 사실 값이 들어가므로 docs/.gitignore 에 ai/ 를 넣는다(pidoc init). 보내기 전에 비밀 검사를 한다.
"""

import subprocess
import time
from pathlib import Path

from .util import COLLECT_FAILED, PidocError, iso, now, sha256_bytes, write_json

PROVIDERS = ("claude", "codex", "none")


def command_for(provider, model=None):
    if provider == "claude":
        argv = ["claude", "-p"]
        if model:
            argv += ["--model", model]
        return argv
    if provider == "codex":
        argv = ["codex", "exec"]
        if model:
            argv += ["-m", model]
        return argv + ["-"]
    raise PidocError(f"모르는 AI: {provider} ({' | '.join(PROVIDERS)})")


def new_record_dir(ai_dir, purpose):
    ai_dir = Path(ai_dir)
    ai_dir.mkdir(parents=True, exist_ok=True)
    base = f"{now().strftime('%Y%m%dT%H%M%S')}-{purpose}"
    name, n = base, 1
    while (ai_dir / name).exists():
        n += 1
        name = f"{base}-{n}"
    path = ai_dir / name
    path.mkdir()
    return path


def check_prompt(cfg, prompt):
    """보내기 전에 비밀 검사(secrets 와 같은 규칙). 걸리면 보내지도 저장하지도 않는다."""
    from .checks.secrets import Scanner
    found = Scanner(cfg).scan(prompt)
    if found:
        lines = "; ".join(f"프롬프트 {n}줄: {msg}" for n, msg in found[:5])
        raise PidocError(f"프롬프트에 공개하면 안 되는 값이 있어 AI 에 보내지 않았습니다 — {lines}"
                         " (틀을 고치거나 [ai] facts 로 보낼 사실을 줄이세요)")


def call(cfg, provider, prompt, purpose):
    """AI 를 부른다. (받은 글 또는 None, 기록 폴더)"""
    settings = cfg.ai
    provider = provider or settings.get("provider", "none")
    model = settings.get("model")
    timeout = settings.get("timeout_s", 600)
    check_prompt(cfg, prompt)
    record = new_record_dir(cfg.ai_dir, purpose)
    data = prompt.encode("utf-8")
    (record / "prompt.txt").write_bytes(data)
    (record / "input.sha256").write_text(sha256_bytes(data) + "\n")
    meta = {"provider": provider, "purpose": purpose, "model": model, "started_at": iso(now())}

    if provider == "none":
        meta["argv"] = None
        write_json(record / "meta.json", meta)
        return None, record

    argv = command_for(provider, model)
    meta["argv"] = argv
    start = time.monotonic()
    try:
        proc = subprocess.run(argv, input=data, capture_output=True, timeout=timeout, cwd=cfg.root)
    except FileNotFoundError:
        meta["error"] = "not_found"
        write_json(record / "meta.json", meta)
        raise PidocError(f"{argv[0]} 를 찾지 못했습니다. 설치했는지, PATH 에 있는지 보세요"
                         f" (오프라인이면 --ai none)", COLLECT_FAILED)
    except subprocess.TimeoutExpired:
        meta["error"] = "timeout"
        write_json(record / "meta.json", meta)
        raise PidocError(f"{argv[0]} 가 {timeout}초 안에 끝나지 않았습니다", COLLECT_FAILED)
    meta.update({
        "finished_at": iso(now()),
        "duration_ms": int((time.monotonic() - start) * 1000),
        "exit": proc.returncode,
        "output_sha256": sha256_bytes(proc.stdout),
    })
    (record / "raw.txt").write_bytes(proc.stdout)
    if proc.stderr:
        (record / "stderr.txt").write_bytes(proc.stderr)
    write_json(record / "meta.json", meta)
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", errors="replace").strip().splitlines()[-3:]
        raise PidocError(f"{argv[0]} 가 실패했습니다(종료 코드 {proc.returncode}): {' / '.join(tail)}", COLLECT_FAILED)
    return proc.stdout.decode("utf-8", errors="replace"), record


def strip_fence(text):
    """응답 전체가 ```markdown ... ``` 로 싸여 있으면 벗긴다."""
    lines = text.strip("\n").splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
        lines = lines[1:-1]
    return "\n".join(lines) + "\n"
