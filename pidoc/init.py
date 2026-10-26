"""pidoc init: 대상 저장소에 docs/ 뼈대와 pidoc.toml 견본을 만든다."""

from pathlib import Path

from .util import PidocError

SAMPLE_TOML = '''\
# pidoc 설정. 자세한 설명은 pidoc 의 README.md 를 보세요.
[project]
name = "{name}"
root = ".."                  # 대상 저장소 루트(이 파일 기준)

[targets.pc]
kind = "local"
alias = "devpc"              # 문서에 나갈 이름. 실제 hostname 은 쓰지 않는다

[collect]
timeout_s = 20
max_output = 1048576         # 바이트. 넘으면 자르고 truncated 로 표시
env_allow = ["PATH", "HOME", "LANG"]
env_set = {{ LC_ALL = "C.UTF-8" }}
allow_programs = ["python3", "uname"]

[[command]]
id = "python_version"
argv = ["python3", "--version"]
targets = ["pc"]
  [[command.fact]]
  key = "system.python_version"
  extract = "regex"
  pattern = 'Python (\\S+)'
  type = "string"

[redact]                     # 수집 직후 증거·사실에 적용(공개용)
hostname = true              # 실제 hostname → 대상 alias
patterns = [ {{ re = '\\b(?:\\d{{1,3}}\\.){{3}}\\d{{1,3}}\\b', to = "<ip>" }} ]
'''

# docs/.gitignore 에 꼭 있어야 하는 줄: 결과물, 가리기 전 원본, 금지어 목록, AI 호출 기록(프롬프트에 값이 들어감)
IGNORE_LINES = ["out/", "evidence/private/", "banned.txt", "ai/"]

FOLDERS = ("src", "facts", "evidence/runs", "ai")


def ensure_gitignore(path):
    """이미 있는 .gitignore 는 덮어쓰지 않고, 빠진 줄만 덧붙인다."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    have = {line.strip() for line in text.splitlines()}
    missing = [line for line in IGNORE_LINES if line not in have]
    if not missing:
        return
    if text and not text.endswith("\n"):
        text += "\n"
    if not text:
        text = "# pidoc: 결과물과 비공개 파일\n"
    path.write_text(text + "\n".join(missing) + "\n", encoding="utf-8")
    print(f"{path.name} 에 더함: {', '.join(missing)}")


def init(repo):
    repo = Path(repo).resolve()
    if not repo.is_dir():
        raise PidocError(f"폴더가 없습니다: {repo}")
    docs = repo / "docs"
    toml = docs / "pidoc.toml"
    if toml.exists():
        raise PidocError(f"이미 있습니다: {toml} (덮어쓰지 않습니다)")
    for folder in FOLDERS:
        (docs / folder).mkdir(parents=True, exist_ok=True)
    toml.write_text(SAMPLE_TOML.format(name=repo.name), encoding="utf-8")
    ensure_gitignore(docs / ".gitignore")
    print(f"만들었습니다: {toml}")
    print("다음: pidoc.toml 의 [[command]] 를 고친 뒤 `pidoc collect`")
    return 0
