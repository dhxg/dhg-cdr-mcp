import importlib.util
import sys
import types
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1] / "server"
sys.path.insert(0, str(SERVER_DIR))
SERVER_FILE = SERVER_DIR / "server.py"


class FakeFastMCP:
    def __init__(self, name):
        self.name = name
        self.registered = []

    def tool(self):
        def decorator(function):
            self.registered.append(function)
            return function
        return decorator


class ServerRegistrationTests(unittest.TestCase):
    def test_http_startup_log_has_no_literal_url_braces(self):
        source = SERVER_FILE.read_text(encoding="utf-8")
        line = next(line for line in source.splitlines() if "Network transport" in line)
        self.assertIn("listening at http://", line)
        self.assertNotIn("{{", line)
        self.assertNotIn("}}", line)

    def load_server(self, module_name):
        spec = importlib.util.spec_from_file_location(module_name, SERVER_FILE)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_compact_profile_registers_all_compact_tools_via_decorator_api(self):
        previous_modules = {
            name: sys.modules.get(name)
            for name in ("fastmcp", "loguru", "dotenv")
        }
        fake_module = types.ModuleType("fastmcp")
        fake_module.FastMCP = FakeFastMCP
        sys.modules["fastmcp"] = fake_module

        fake_loguru = types.ModuleType("loguru")
        fake_loguru.logger = type(
            "Logger",
            (),
            {
                "remove": lambda self: None,
                "add": lambda self, *args, **kwargs: None,
                "info": lambda self, *args, **kwargs: None,
                "warning": lambda self, *args, **kwargs: None,
            },
        )()
        sys.modules["loguru"] = fake_loguru

        fake_dotenv = types.ModuleType("dotenv")
        fake_dotenv.load_dotenv = lambda *args, **kwargs: None
        sys.modules["dotenv"] = fake_dotenv
        try:
            module = self.load_server("coreldraw_mcp_server_fake")
            module.register_tools()
            self.assertEqual(module.mcp.name, "coreldraw-live")
            self.assertEqual(len(module.mcp.registered), 26)
            names = {f.__name__ for f in module.mcp.registered}
            self.assertIn("batch_search_images", names)
            self.assertIn("batch_search_and_place", names)
        finally:
            for name, previous in previous_modules.items():
                if previous is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = previous

    def test_compact_tools_register_on_installed_fastmcp(self):
        if importlib.util.find_spec("fastmcp") is None:
            self.skipTest("FastMCP is not installed in this environment")
        module = self.load_server("coreldraw_mcp_server_real")
        module.register_tools()


if __name__ == "__main__":
    unittest.main()
