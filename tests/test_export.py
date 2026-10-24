import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from tools import export as export_tools


class Status:
    connected = True


class Collection:
    def __init__(self, values):
        self.values = values
    @property
    def Count(self):
        return len(self.values)
    def __iter__(self):
        return iter(self.values)


class Layer:
    def __init__(self, visible, printable):
        self.Visible = visible
        self.Printable = printable


class Page:
    def __init__(self):
        self.SizeWidth = 210.0
        self.SizeHeight = 297.0
        self.Index = 1
        self.Shapes = Collection([object()])
        self.Layers = Collection([Layer(False, False), Layer(True, False)])
    def Activate(self):
        return None


class Settings:
    pass


class ExportFilter:
    def __init__(self, path):
        self.path = path
    def Finish(self):
        Path(self.path).write_bytes(b"exported")


class Document:
    def __init__(self):
        self.ActivePage = Page()
        self.Unit = 3
        self.PDFSettings = Settings()
        self.clear_selection_calls = 0
    def ClearSelection(self):
        self.clear_selection_calls += 1
    def PublishToPDF(self, path):
        Path(path).write_bytes(b"pdf")
    def Export(self, path, *args):
        Path(path).write_bytes(b"export")
    def ExportEx(self, path, *args):
        raise RuntimeError("exercise documented fallback")
    def ExportBitmap(self, path, *args):
        return ExportFilter(path)


class App:
    def __init__(self, doc):
        self.ActiveDocument = doc
    def CreateRect(self, *args):
        return args


class Connection:
    def __init__(self):
        self.status = Status()
        self.doc = Document()
        self.app = App(self.doc)
        self.timeouts = []
    def safe_call(self, func, *args, **kwargs):
        self.timeouts.append(kwargs.get("timeout"))
        try:
            return {"success": True, "result": func(*args)}
        except Exception as exc:
            return {"success": False, "result": None, "error": str(exc)}


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.conn = Connection()
        self.original_get_connection = export_tools.get_connection
        export_tools.get_connection = lambda: self.conn
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        export_tools.get_connection = self.original_get_connection
        self.temp_dir.cleanup()

    def path(self, name):
        return str(Path(self.temp_dir.name) / name)

    def test_all_single_export_functions_execute_without_closure_errors(self):
        calls = [
            (export_tools.export_pdf, self.path("a.pdf")),
            (export_tools.export_dxf, self.path("a.dxf")),
            (export_tools.export_ai, self.path("a.ai")),
            (export_tools.export_svg, self.path("a.svg")),
            (export_tools.export_png, self.path("a.png")),
            (export_tools.export_jpeg, self.path("a.jpg")),
            (export_tools.export_preview_png, self.path("preview.png")),
        ]
        for function, path in calls:
            with self.subTest(function=function.__name__):
                result = function(path)
                self.assertTrue(result.success, result.error)
                self.assertGreater(Path(path).stat().st_size, 0)
        self.assertEqual(self.conn.timeouts, [300.0] * len(calls))

    def test_preview_does_not_change_layer_state_or_selection(self):
        before = [(layer.Visible, layer.Printable) for layer in self.conn.doc.ActivePage.Layers]
        result = export_tools.export_preview_png(self.path("preview.png"))
        after = [(layer.Visible, layer.Printable) for layer in self.conn.doc.ActivePage.Layers]
        self.assertTrue(result.success, result.error)
        self.assertEqual(before, after)
        self.assertEqual(self.conn.doc.clear_selection_calls, 0)


if __name__ == "__main__":
    unittest.main()
