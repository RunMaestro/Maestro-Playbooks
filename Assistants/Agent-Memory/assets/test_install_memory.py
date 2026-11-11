"""Tests for install_memory.py: a full install into a throwaway vault, without Maestro, a model or search.

Run: python3 test_install_memory.py   (needs PyYAML, like the tools it installs)
Spec 2026-11-10.10.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(tmp: Path, *extra) -> subprocess.CompletedProcess:
    env = os.environ | {"HOME": str(tmp / "home")}
    return subprocess.run([sys.executable, str(HERE / "install_memory.py"), "all", "--owner", "Alex",
                           "--vault", str(tmp / "vault"), "--out", str(tmp / "out"), "--agent-name", "Test Bot",
                           "--no-maestro", "--no-model", "--search", "none", *extra],
                          capture_output=True, text=True, env=env, timeout=600)


def test_fresh_install_verifies_and_keeps_user_text():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        (t / "vault").mkdir()
        (t / "vault" / "CLAUDE.md").write_text("# my own rules\n")
        r = run(t)
        assert r.returncode == 0, r.stdout[-800:] + r.stderr[-400:]
        assert "Memory Verify: VERIFIED" in (t / "out" / "MEMORY_VERIFY.md").read_text()
        claude = (t / "vault" / "CLAUDE.md").read_text()
        assert claude.startswith("# my own rules") and claude.count("agent-memory:begin") == 1
        cfg = json.loads((t / "vault" / "Agent" / "Memory" / "config.json").read_text())
        assert cfg["promote"]["mode"] == "dry-run" and cfg["promote"]["reviewed"] is False
        assert (t / "out" / "MEMORY_MANUAL_STEPS.md").exists()          # no Maestro: capture lines handed over


def test_rerun_is_idempotent():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        (t / "vault").mkdir()
        assert run(t).returncode == 0
        store = t / "vault" / "Agent" / "Memory" / "Store"
        before = (store / "MEMORY.md").read_text()
        assert run(t).returncode == 0
        assert (store / "MEMORY.md").read_text() == before
        assert (t / "vault" / "CLAUDE.md").read_text().count("agent-memory:begin") == 1
        journal = next((t / "vault" / "Agent" / "Journal").glob("*.md")).read_text()
        assert journal.count("## Memory installed") == 1
        assert not list((t / "vault" / "Agent" / "Tools").glob("*.new"))


def test_user_edited_tool_is_kept():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        (t / "vault").mkdir()
        assert run(t).returncode == 0
        tool = t / "vault" / "Agent" / "Tools" / "memory_lint.py"
        tool.write_text(tool.read_text() + "\n# my local tweak\n")
        assert run(t).returncode == 0
        assert "# my local tweak" in tool.read_text()
        assert (tool.parent / "memory_lint.py.new").exists()


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, e)
    print(f"{fails} failed" if fails else "all passed")
    sys.exit(1 if fails else 0)
