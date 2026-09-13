"""Serial native protocol clients. Python stdlib; no credentials, network listeners or LLM polling.

Codex: JSONL app-server V2. Pi: RPC JSONL, default completion=agent_settled.
A process can host many turns. A protocol completion is NOT process exit or AC pass.
"""

from __future__ import annotations

import contextlib
import json
import os
import queue
import signal
import subprocess
import threading
import time
from pathlib import Path


def replace_snapshot(source: Path, destination: Path) -> None:
    """Allow brief Windows readers to close; persistent access denial still fails."""
    for attempt in range(6):
        try:
            os.replace(source, destination)
            return
        except PermissionError as exc:
            if os.name != "nt" or exc.winerror not in {5, 32, 33} or attempt == 5:
                raise
            # Windows readers without FILE_SHARE_DELETE briefly prevent replacement.
            time.sleep(0.01 * 2**attempt)


class ProtocolError(RuntimeError):
    pass


class NeedsInput(ProtocolError):
    pass


def terminate(proc):
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)


class JsonLines:
    """Read one wire stream continuously; match responses without losing early notifications."""

    def __init__(self, argv, cwd: Path, log_dir: Path):
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir = log_dir
        self.queue = queue.Queue()
        self.backlog = []
        self.serial = 0
        self.write_lock = threading.Lock()
        self.callback = lambda _message: None
        self.stderr = (log_dir / "stderr.log").open("ab")
        env = os.environ.copy()
        env.pop("CODEX_THREAD_ID", None)
        env["AI_FLOW_CHILD"] = "1"
        options = (
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if os.name == "nt"
            else {"start_new_session": True}
        )
        try:
            self.proc = subprocess.Popen(
                argv,
                cwd=str(cwd),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self.stderr,
                text=True,
                encoding="utf-8",
                errors="strict",
                bufsize=1,
                shell=False,
                env=env,
                **options,
            )
        except BaseException:
            self.stderr.close()
            raise
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            with (self.log_dir / "wire.jsonl").open("a", encoding="utf-8") as log:
                for line in self.proc.stdout:
                    if not line.strip():
                        continue
                    log.write(line)
                    log.flush()
                    try:
                        value = json.loads(line)
                        if not isinstance(value, dict):
                            raise ValueError("Wire message must be an object")
                    except ValueError as exc:
                        self.queue.put(
                            ProtocolError(
                                "Non-JSON protocol output; inspect local wire log: " + str(exc)
                            )
                        )
                        return
                    self.queue.put(value)
        except Exception as exc:
            self.queue.put(ProtocolError("Protocol reader failed: " + str(exc)))
        finally:
            self.queue.put(EOFError("Agent transport closed before a protocol completion."))

    def next_id(self):
        self.serial += 1
        return "flow-" + str(self.serial)

    def send(self, value):
        with self.write_lock:
            try:
                self.proc.stdin.write(json.dumps(value, ensure_ascii=False) + "\n")
                self.proc.stdin.flush()
            except (OSError, ValueError) as exc:
                raise ProtocolError("Unable to write to agent transport") from exc

    def receive(self, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Protocol operation deadline exceeded")
        try:
            value = self.queue.get(
                timeout=remaining
            )  # waits for wire data, not agent status queries
        except queue.Empty as exc:
            raise TimeoutError("No protocol completion before deadline") from exc
        if isinstance(value, BaseException):
            raise value
        self.callback(value)
        self._deny_interaction(value)
        return value

    def _deny_interaction(self, value):
        if "method" in value and "id" in value and value.get("type") != "extension_ui_request":
            method = value["method"]
            if method in {
                "item/commandExecution/requestApproval",
                "item/fileChange/requestApproval",
            }:
                self.send({"id": value["id"], "result": {"decision": "decline"}})
            elif method == "item/permissions/requestApproval":
                self.send({"id": value["id"], "result": {"permissions": {}, "scope": "turn"}})
            elif method == "mcpServer/elicitation/request":
                self.send({"id": value["id"], "result": {"action": "decline", "content": None}})
            else:
                self.send(
                    {
                        "id": value["id"],
                        "error": {
                            "code": -32601,
                            "message": "This unattended client does not grant approval or answer interactive requests.",
                        },
                    }
                )
            raise NeedsInput(
                "Server requested input/approval: " + method + "; no permission was granted."
            )
        if value.get("type") == "extension_ui_request" and value.get("method") in {
            "select",
            "confirm",
            "input",
            "editor",
        }:
            self.send({"type": "extension_ui_response", "id": value["id"], "cancelled": True})
            raise NeedsInput(
                "Pi extension requested user input; cancelled without granting permission."
            )

    def request(self, kind, params, timeout=30, pi=False):
        rid = self.next_id()
        message = (
            {"id": rid, "type": kind, **params}
            if pi
            else {"id": rid, "method": kind, "params": params}
        )
        self.send(message)
        deadline = time.monotonic() + timeout
        while True:
            value = self.receive(deadline)
            if value.get("id") == rid and (
                "result" in value or "error" in value or value.get("type") == "response"
            ):
                if value.get("error") is not None or (pi and value.get("success") is not True):
                    raise ProtocolError(
                        str(value.get("error", "Command was not acknowledged successfully"))
                    )
                return value.get("data", {}) if pi else value.get("result", {})
            self.backlog.append(value)  # notifications may legally precede the response

    def event(self, deadline):
        if self.backlog:
            return self.backlog.pop(0)
        return self.receive(deadline)

    def close(self):
        # These are our own children, never a PID loaded from a possibly stale state file.
        with contextlib.suppress(OSError, ValueError):
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            terminate(self.proc)
            self.proc.wait(timeout=10)
        self.reader.join(timeout=2)
        self.proc.stdout.close()
        self.stderr.close()


class CodexClient:
    def __init__(self, argv, root, folder, cfg):
        self.wire = JsonLines(
            argv + cfg.get("codex_global_args", []) + ["app-server"], root, folder
        )
        self.root, self.cfg = root, cfg
        self.thread_id = self.turn_id = None
        try:
            self.wire.request(
                "initialize",
                {
                    "clientInfo": {
                        "name": "ai_flow_native",
                        "title": "AI Flow Native",
                        "version": "3.2.0",
                    }
                },
            )
            self.wire.send({"method": "initialized", "params": {}})
        except BaseException:
            self.wire.close()
            raise

    def select_thread(self, thread_id, role):
        self.turn_id = None
        params = {
            "cwd": str(self.root),
            "approvalPolicy": "never",
            "sandbox": "workspace-write" if role == "CODEX" else "read-only",
        }
        if self.cfg.get("codex_model"):
            params["model"] = self.cfg["codex_model"]
        if self.cfg.get("codex_model_provider"):
            params["modelProvider"] = self.cfg["codex_model_provider"]
        if thread_id:
            params["threadId"] = thread_id
        result = self.wire.request("thread/resume" if thread_id else "thread/start", params)
        actual = result.get("thread", {}).get("id")
        if not actual or (thread_id and actual != thread_id):
            raise ProtocolError("Missing or mismatched Codex thread ID")
        self.thread_id = actual
        self.identity = {
            "thread_id": actual,
            "model": result.get("model"),
            "model_provider": result.get(
                "modelProvider", result.get("thread", {}).get("modelProvider")
            ),
        }
        return actual

    def interrupt(self):
        if self.thread_id and self.turn_id:
            self.wire.send(
                {
                    "id": self.wire.next_id(),
                    "method": "turn/interrupt",
                    "params": {"threadId": self.thread_id, "turnId": self.turn_id},
                }
            )

    def run(self, prompt, role, schema, timeout, on_identity):
        policy = (
            {
                "type": "workspaceWrite",
                "writableRoots": [str(self.root)],
                "networkAccess": self.cfg.get("codex_network_access", False),
            }
            if role == "CODEX"
            else {"type": "readOnly"}
        )
        params = {
            "threadId": self.thread_id,
            "input": [{"type": "text", "text": prompt}],
            "cwd": str(self.root),
            "approvalPolicy": "never",
            "sandboxPolicy": policy,
        }
        if schema:
            params["outputSchema"] = schema
        if self.cfg.get("codex_effort"):
            params["effort"] = self.cfg["codex_effort"]
        started = self.wire.request("turn/start", params, timeout=min(30, timeout))
        self.turn_id = started.get("turn", {}).get("id")
        if not self.turn_id:
            raise ProtocolError("Missing turn ID in turn/start response")
        on_identity({"thread_id": self.thread_id, "turn_id": self.turn_id})
        deadline = time.monotonic() + timeout
        texts = {}
        final_ids = []
        completion = None
        while completion is None:
            value = self.wire.event(deadline)
            method, p = value.get("method"), value.get("params", {})
            if p.get("threadId") not in (None, self.thread_id):
                continue
            # Never let another turn's completion release the next writer.
            if p.get("turnId") not in (None, self.turn_id):
                continue
            if method == "item/completed":
                item = p.get("item", {})
                if item.get("type") == "agentMessage" and isinstance(item.get("text"), str):
                    iid = item.get("id", str(len(texts)))
                    texts[iid] = item["text"]
                    if item.get("phase") == "final_answer":
                        final_ids.append(iid)
            if method == "turn/completed" and p.get("turn", {}).get("id") == self.turn_id:
                completion = p["turn"]
        # Completed items are authoritative. Never turn a streamed partial answer into success.
        for item in completion.get("items", []):
            if item.get("type") == "agentMessage" and isinstance(item.get("text"), str):
                iid = item.get("id", str(len(texts)))
                texts[iid] = item["text"]
                if item.get("phase") == "final_answer":
                    final_ids.append(iid)
        report = texts[final_ids[-1]] if final_ids else (list(texts.values())[-1] if texts else "")
        status = completion.get("status")
        return {
            "report": report,
            "ok": status == "completed" and bool(report.strip()),
            "metadata": {
                "completed_event": True,
                "completion_event": "turn/completed",
                "turn_status": status,
                "thread_id": self.thread_id,
                "turn_id": self.turn_id,
                "error": completion.get("error"),
                **self.identity,
            },
        }

    def close(self):
        self.wire.close()


class PiClient:
    def __init__(self, argv, root, folder, cfg):
        self.cfg, self.root, self.folder = cfg, root, folder
        sessions = folder / "sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        self.wire = JsonLines(
            argv + cfg.get("pi_args", []) + ["--mode", "rpc", "--session-dir", str(sessions)],
            root,
            folder,
        )
        self.task = None
        try:
            self.state = self.wire.request("get_state", {}, pi=True)
            if self.state.get("isStreaming") or self.state.get("isCompacting"):
                raise ProtocolError("New Pi process is unexpectedly busy")
        except BaseException:
            self.wire.close()
            raise

    def select_session(self, task, known_file=None):
        if self.task != task:
            data = (
                self.wire.request("switch_session", {"sessionPath": known_file}, pi=True)
                if known_file
                else self.wire.request("new_session", {}, pi=True)
            )
            if data.get("cancelled"):
                raise NeedsInput("Pi session switch was cancelled by an extension")
            self.task = task
        self.state = self.wire.request("get_state", {}, pi=True)
        if (
            self.state.get("isStreaming")
            or self.state.get("isCompacting")
            or self.state.get("pendingMessageCount", 0)
        ):
            raise ProtocolError("Pi session must be idle with an empty queue before dispatch")
        return self.state

    def interrupt(self):
        # RPC is asynchronous. clear_queue before abort prevents a queued continuation after abort.
        for kind in ["clear_queue", "abort"]:
            self.wire.send({"id": self.wire.next_id(), "type": kind})

    def run(self, prompt, timeout, on_identity):
        self.wire.request("prompt", {"message": prompt}, timeout=min(30, timeout), pi=True)
        deadline = time.monotonic() + timeout
        final = None
        completion_event = self.cfg.get("pi_completion_event", "agent_settled")
        while True:
            value = self.wire.event(deadline)
            kind = value.get("type")
            if kind == "message_end" and value.get("message", {}).get("role") == "assistant":
                final = value["message"]
            if kind == "agent_end":
                for message in value.get("messages", []):
                    if message.get("role") == "assistant":
                        final = message
            if kind == completion_event:
                if kind == "agent_end" and value.get("willRetry"):
                    continue
                break
        # One boundary read, not a polling loop. Check quiescence and persist session identity.
        state = self.wire.request("get_state", {}, pi=True)
        if (
            state.get("isStreaming")
            or state.get("isCompacting")
            or state.get("pendingMessageCount", 0)
        ):
            raise ProtocolError(
                "Pi completion arrived but session is not idle; no next writer permitted"
            )
        model = state.get("model") or {}
        on_identity(
            {
                "session_id": state.get("sessionId"),
                "session_file": state.get("sessionFile"),
                "model": model.get("id"),
                "provider": model.get("provider"),
            }
        )
        final = final or {}
        content = final.get("content", [])
        report = (
            content
            if isinstance(content, str)
            else "\n".join(x.get("text", "") for x in content if x.get("type") == "text")
        )
        reason = final.get("stopReason")
        return {
            "report": report,
            "ok": bool(report.strip()) and reason not in {"error", "aborted", "length"},
            "metadata": {
                "completed_event": True,
                "completion_event": completion_event,
                "stop_reason": reason,
                "session_id": state.get("sessionId"),
                "session_file": state.get("sessionFile"),
                "model": final.get("model", model.get("id")),
                "provider": final.get("provider", model.get("provider")),
            },
        }

    def close(self):
        self.wire.close()


class NativePool:
    """One Codex server and one Pi RPC process per runner lifetime, serial turns only."""

    def __init__(self, root, folder, cfg):
        self.root, self.folder, self.cfg = root, folder, cfg
        self.codex = self.pi = None
        self.active = None
        self.closed = False

    def execute(self, role, prompt, directory, timeout, state, save, schema=None, task=""):
        started = time.time()
        (directory / "prompt.txt").write_text(prompt, encoding="utf-8")
        last_progress = 0.0

        def identity(fields):
            state["pending"].update(fields)
            save()

        def progress(value):
            nonlocal last_progress
            kind = value.get("method") or value.get("type")
            stamp = time.monotonic()
            if ("delta" in str(kind) or kind == "message_update") and stamp - last_progress < 0.3:
                return
            last_progress = stamp
            # No prompt/token/credential contents in the display projection.
            data = {
                "event": kind,
                "at_unix": time.time(),
                "pid": self.active.wire.proc.pid,
                "role": role,
                "task_id": task,
            }
            p = value.get("params", {})
            item = p.get("item", {})
            data["tool"] = item.get("type") or value.get("toolName")
            tmp = directory / "progress.tmp"
            tmp.write_text(json.dumps(data), encoding="utf-8")
            replace_snapshot(tmp, directory / "progress.json")

        cancelled = threading.Event()
        finished = threading.Event()
        watchdog = None
        try:
            if role == "PI":
                if self.pi is None:
                    self.pi = PiClient(
                        self.cfg["pi_command"], self.root, self.folder / "protocol/pi", self.cfg
                    )
                client = self.pi
            else:
                if self.codex is None:
                    self.codex = CodexClient(
                        self.cfg["codex_command"],
                        self.root,
                        self.folder / "protocol/codex",
                        self.cfg,
                    )
                client = self.codex
            self.active = client
            client.wire.callback = progress
            identity(
                {
                    "child_pid": client.wire.proc.pid,
                    "protocol": "pi-rpc" if role == "PI" else "codex-app-server",
                    "transport_log": str(client.wire.log_dir),
                    "started_at_unix": started,
                }
            )
            sessions = state.setdefault("native_sessions", {"codex": {}, "pi": {}})
            if role == "PI":
                current = client.select_session(task, sessions["pi"].get(task))
                identity(
                    {
                        "session_id": current.get("sessionId"),
                        "session_file": current.get("sessionFile"),
                    }
                )
            else:
                # Controller and each worker retain separate threads. Every review starts a fresh one.
                key = "controller" if role == "CONTROLLER" else "worker:" + task
                thread = client.select_thread(
                    None if role == "REVIEW" else sessions["codex"].get(key), role
                )
                if role != "REVIEW":
                    sessions["codex"][key] = thread
                identity({"thread_id": thread})

            def cancel_watch():
                # This checks only an explicit LOCAL cancellation marker, never a model/agent/CI status.
                # Protocol progress/completion itself is entirely push driven.
                while not finished.wait(0.25):
                    if (self.folder / "CANCEL").exists():
                        cancelled.set()
                        with contextlib.suppress(Exception):
                            client.interrupt()
                        if not finished.wait(5):
                            terminate(client.wire.proc)
                        return

            watchdog = threading.Thread(target=cancel_watch, daemon=True)
            watchdog.start()
            result = (
                client.run(prompt, timeout, identity)
                if role == "PI"
                else client.run(prompt, role, schema, timeout, identity)
            )
            if role == "PI" and result["metadata"].get("session_file"):
                sessions["pi"][task] = result["metadata"]["session_file"]
                save()
            result.update({"exit_code": None, "timed_out": False, "cancelled": cancelled.is_set()})
            if cancelled.is_set():
                result["ok"] = False
            return result
        except (Exception, KeyboardInterrupt) as exc:
            client = self.active
            code = client.wire.proc.poll() if client else None
            if client:
                with contextlib.suppress(Exception):
                    client.interrupt()
                # Fail closed: do not reuse a transport after EOF, timeout, malformed data or input request.
                with contextlib.suppress(Exception):
                    client.close()
                code = client.wire.proc.poll()
                if code is None:
                    raise ProtocolError(
                        "Agent transport could not be stopped; dispatch halted. Inspect owned PID "
                        + str(client.wire.proc.pid)
                    ) from exc
                if role == "PI":
                    self.pi = None
                else:
                    self.codex = None
            if isinstance(exc, KeyboardInterrupt):
                raise
            return {
                "report": "",
                "ok": False,
                "exit_code": code,
                "timed_out": isinstance(exc, TimeoutError),
                "cancelled": cancelled.is_set(),
                "metadata": {
                    "completed_event": False,
                    "needs_input": isinstance(exc, NeedsInput),
                    "error": type(exc).__name__ + ": " + str(exc),
                },
            }
        finally:
            finished.set()
            if watchdog:
                watchdog.join(timeout=2)
            self.active = None

    def close(self):
        if self.closed:
            return
        for client in (self.codex, self.pi):
            if client:
                with contextlib.suppress(Exception):
                    client.close()
        self.closed = True
