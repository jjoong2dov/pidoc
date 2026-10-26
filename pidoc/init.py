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
'''

GITIGNORE = """\
# pidoc: 결과물과 비공개 파일
out/
evidence/private/
banned.txt
"""

FOLDERS = ("src", "facts", "evidence/runs", "ai")


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
    ignore = docs / ".gitignore"
    if not ignore.exists():
        ignore.write_text(GITIGNORE, encoding="utf-8")
    print(f"만들었습니다: {toml}")
    print("다음: pidoc.toml 의 [[command]] 를 고친 뒤 `pidoc collect`")
    return 0
