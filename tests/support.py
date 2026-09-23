"""Test helpers: a throwaway configuration, and bin/ tools loaded as modules.

The tools read fleet.toml at import time, so every tool is imported with
FLEET_CONFIG pointing at a temporary directory -- never at the real one.
"""
import importlib.machinery, importlib.util, os, sys, tempfile, textwrap

# No bytecode caches. A cache is revalidated by source mtime (whole seconds) and
# size, so an edit and its revert inside one second at equal size -- routine when
# breaking a guard to prove its test fails -- runs the stale edited code. Seen
# 2026-09-13: the result of an earlier edit reported against the restored file.
sys.dont_write_bytecode = True

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP not in sys.path:
    sys.path.insert(0, APP)

BASE_TOML = """
[paths]
state = "{state}"

[colors]
alpha = "red"
beta  = "blue"

[cluster.testcluster]
ssh_host     = "nowhere.invalid"
user         = "tester"
job_id_re    = "[0-9]{{6,9}}"
held_reasons = ["JobHeldUser", "JobHeldAdmin"]

[owners]
"/proj-a-sweep" = "alpha-runs"
"/proj-a"       = "alpha"
"""

class FakeConfig:
    """A config dir with fleet.toml, a state dir and a briefs dir, set as FLEET_CONFIG."""
    def __init__(self, toml=None, briefs=("alpha",)):
        self._tmp = tempfile.TemporaryDirectory(prefix="fleet-test-")
        self.root = self._tmp.name
        self.config = os.path.join(self.root, "config")
        self.state = os.path.join(self.root, "state")
        os.makedirs(os.path.join(self.config, "briefs"))
        os.makedirs(self.state)
        with open(os.path.join(self.config, "fleet.toml"), "w") as f:
            f.write(textwrap.dedent(toml if toml is not None else BASE_TOML)
                    .format(state=self.state))
        for b in briefs:
            with open(os.path.join(self.config, "briefs", f"{b}.md"), "w") as f:
                f.write("# brief\n")
        self._old = os.environ.get("FLEET_CONFIG")
        os.environ["FLEET_CONFIG"] = self.config

    def close(self):
        if self._old is None:
            os.environ.pop("FLEET_CONFIG", None)
        else:
            os.environ["FLEET_CONFIG"] = self._old
        self._tmp.cleanup()

def load_tool(name):
    """Import bin/<name> (no .py extension) as a fresh module."""
    path = os.path.join(APP, "bin", name)
    loader = importlib.machinery.SourceFileLoader(f"tool_{name}", path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod
