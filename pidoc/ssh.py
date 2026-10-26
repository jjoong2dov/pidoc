"""ssh 대상: 허용 목록을 보고, 원격 명령을 한 줄로 만든다."""

import shlex


def allowed(target, argv):
    # 보안 경계가 아니라 실수 방지. argv[0] 이 목록과 글자 그대로 같아야 한다.
    return argv[0] in target.allow_programs


def ssh_argv(target, argv):
    return [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={target.known_hosts}",
        "--", target.host,
        shlex.join(argv),
    ]
