"""Tests for install_memory.py: a full install into a throwaway vault, without Maestro, a model or search.

Run: python3 test_install_memory.py   (needs PyYAML, like the tools it installs)
Spec 2026-11-10.10; 2026-11-10.11 adds the review fixes (R1 to R11).
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(tmp: Path, *extra, vault: Path | None = None, cmd: str = "all") -> subprocess.CompletedProcess:
    env = os.environ | {"HOME": str(tmp / "home")}
    return subprocess.run([sys.executable, str(HERE / "install_memory.py"), cmd, "--owner", "Alex",
                           "--vault", str(vault or tmp / "vault"), "--out", str(tmp / "out"), "--agent-name", "Test Bot",
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



def test_folder_outside_the_vault_blocks():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        (t / "vault").mkdir()
        r = run(t, "--agent-folder", "../elsewhere", cmd="plan")
        assert r.returncode == 2 and "inside the vault" in r.stdout
        assert not (t / "elsewhere").exists()


def test_vault_path_with_a_space_is_quoted_in_schedules():
    import shlex
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        v = t / "My Vault"
        v.mkdir()
        assert run(t, vault=v, cmd="plan").returncode == 0
        plan = json.loads((t / "out" / "MEMORY_PLAN.json").read_text())
        for sub in plan["cue_subscriptions"]:
            words = shlex.split(sub["command"]["shell"])
            assert f"AGENT_VAULT={v.resolve()}" in words, sub["name"]


def test_tools_from_before_the_installer_are_backed_up():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        tools = t / "vault" / "Agent" / "Tools"
        tools.mkdir(parents=True)
        (tools / "memory_lint.py").write_text("# an older, possibly edited copy\n")
        assert run(t).returncode == 0
        backups = list(tools.glob("memory_lint.py.before-*"))
        assert backups and "older" in backups[0].read_text()


def test_edited_rules_file_is_kept():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        (t / "vault").mkdir()
        assert run(t).returncode == 0
        rule = t / "vault" / "Agent" / "Rules" / "journal.md"
        rule.write_text(rule.read_text() + "\n- my own journal rule\n")
        assert run(t).returncode == 0
        assert "my own journal rule" in rule.read_text() and (rule.parent / "journal.md.new").exists()

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
