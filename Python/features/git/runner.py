"""Binary-safe cancellable execution. Reuses commonUtils process-tree cleanup.

Commands never go through a shell. Temporary output files avoid pipe deadlocks and
unbounded capture; stderr is streamed separately from machine-readable stdout.
"""

from dataclasses import dataclass
import os
import re
import shutil
from threading import Event

from commonUtils.integrations.wrappers.cmdShellWrapper.capture import (
    run_captured,
    CommandStartError,
    CommandTimeout,
)
from commonUtils.runtime.operations import OperationCancelled
from commonUtils.runtime.diagnostics.redaction import redact


class GitError(RuntimeError):
    pass


class GitCancelled(GitError):
    pass


@dataclass(frozen=True)
class CommandResult:
    stdout: bytes
    stderr: str
    returncode: int
    truncated: bool = False


class GitRunner:
    def __init__(self, executable="git", *, cancel=None, progress=None, timeout=120):
        self.executable = executable or "git"
        self.cancel = cancel or Event()
        self.progress = progress or (lambda text: None)
        self.timeout = timeout
        self.config_options = {}
        self.diff_limit = 1024 * 1024
        self.author_date = False
        self.keep_backups = False
        self.no_ff = False
        self.check_submodules = False
        self.push_tags = False

    def version(self):
        text = self.run(["--version"]).stdout.decode("utf-8", "replace").strip()
        match = re.search(r"git version (\d+)\.(\d+)", text)
        if not match or tuple(map(int, match.groups())) < (2, 40):
            raise GitError(
                f"Git 2.40 or newer is required; found {text or 'an unknown version'}."
            )
        return text

    def run(
        self,
        arguments,
        *,
        cwd=None,
        check=True,
        limit=8 * 1024 * 1024,
        timeout=None,
        input_data=None,
        external=None,
        sensitive=False,
    ):
        if self.cancel.is_set():
            raise GitCancelled("Operation cancelled.")
        program = shutil.which(external or self.executable)
        if program is None:
            raise GitError(
                "Git executable not found. Install Git or set its path in Git settings."
            )
        defaults = [
            part
            for key, value in self.config_options.items()
            for entry in (value if isinstance(value, list) else [value])
            for part in ("-c", key + "=" + entry)
        ]
        command = (
            [program, *map(str, arguments)]
            if external
            else [
                program,
                "--no-pager",
                "--literal-pathspecs",
                "-c",
                "color.ui=false",
                "-c",
                "core.quotepath=false",
                *defaults,
                *map(str, arguments),
            ]
        )
        env = os.environ.copy()
        # Do not let another repository's shell environment redirect this workspace.
        for key in (
            "GIT_DIR",
            "GIT_WORK_TREE",
            "GIT_INDEX_FILE",
            "GIT_COMMON_DIR",
            "GIT_OBJECT_DIRECTORY",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            "GIT_NAMESPACE",
        ):
            env.pop(key, None)
        # Background status/diff reads must not rewrite the index and trigger
        # our filesystem watcher again. Required locks for mutations still work.
        env.update(
            GIT_TERMINAL_PROMPT="0",
            GCM_INTERACTIVE="never",
            LC_ALL="C",
            GIT_OPTIONAL_LOCKS="0",
        )
        if sensitive:
            for key in list(env):
                if key.startswith("GIT_TRACE") or key == "GCM_TRACE_SECRETS":
                    env.pop(key, None)
        if self.config_options.get("credential.credentialStore"):
            env["GCM_CREDENTIAL_STORE"] = self.config_options[
                "credential.credentialStore"
            ]
        # SSH agents and configured credential helpers remain available. Never wait
        # for an invisible terminal prompt; host-key/password setup happens outside.
        if "GIT_SSH_COMMAND" not in env and "GIT_SSH" not in env:
            env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"
        duration = self.timeout if timeout is None else timeout
        if input_data is not None and len(input_data) > 4096:
            raise GitError("Input exceeds the supported size.")
        try:
            captured = run_captured(
                command,
                cwd=cwd,
                environment=env,
                input_data=input_data,
                limit=limit,
                timeout=duration,
                cancelled=self.cancel.is_set,
                progress=lambda chunk: self.progress(
                    redact(chunk.decode("utf-8", "replace"))
                ),
                discard_output=sensitive,
            )
        except CommandStartError as error:
            raise GitError(redact(str(error))) from error
        except OperationCancelled as error:
            raise GitCancelled(
                "Operation cancelled. Refresh to inspect repository state."
            ) from error
        except CommandTimeout as error:
            raise GitError(
                "Git operation timed out. Refresh to inspect repository state."
            ) from error
        code = captured.returncode
        stderr = (
            ("Credential operation failed." if code else "")
            if sensitive
            else redact(captured.stderr.decode("utf-8", "replace"))
        )
        if not hasattr(os, "pread") and stderr:
            self.progress(stderr)
        result = CommandResult(captured.stdout, stderr, code, captured.truncated)
        if check and code:
            raise GitError(stderr.strip() or f"Git exited with code {code}.")
        if check and result.truncated:
            raise GitError(
                "Git response exceeded the capture limit. Narrow the selection and try again."
            )
        return result
