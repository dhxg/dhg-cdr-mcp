import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from core import sessions


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
    def __call__(self, index):
        return self.values[index - 1]


class EmptyDocuments:
    Count = 0


class EmptyApp:
    Documents = EmptyDocuments()
    @property
    def ActiveDocument(self):
        raise RuntimeError("No active document")


class EmptyConnection:
    status = Status()
    app = EmptyApp()
    def is_alive(self):
        return True
    def safe_call(self, func, *args, **kwargs):
        try:
            return {"success": True, "result": func(*args)}
        except Exception as exc:
            return {"success": False, "result": None, "error": str(exc)}


class Shape:
    def __init__(self):
        self.StaticID = 1
        self.Name = "shape"
        self.PositionX = 10.0
        self.PositionY = 20.0
        self.SizeWidth = 30.0
        self.SizeHeight = 40.0


class Page:
    Index = 1
    SizeWidth = 210.0
    SizeHeight = 297.0
    def __init__(self):
        self.Shapes = Collection([Shape()])


class Document:
    FileName = "test.cdr"
    FilePath = "/tmp"
    Name = "test.cdr"
    Modified = False
    Unit = 3
    def __init__(self):
        self.ActivePage = Page()
        self.Pages = Collection([self.ActivePage])
        self.begin_calls = 0
        self.end_calls = 0
        self.undo_calls = 0
    def Activate(self):
        return None
    def BeginCommandGroup(self, label):
        self.begin_calls += 1
    def EndCommandGroup(self):
        self.end_calls += 1
    def Undo(self):
        self.undo_calls += 1


class App:
    def __init__(self, document):
        self.Documents = Collection([document])
        self.ActiveDocument = document
        self.Optimization = False
    def Refresh(self):
        return None


class DocumentConnection:
    status = Status()
    def __init__(self, document):
        self.app = App(document)
    def is_alive(self):
        return True
    def safe_call(self, func, *args, **kwargs):
        try:
            return {"success": True, "result": func(*args)}
        except Exception as exc:
            return {"success": False, "result": None, "error": str(exc)}


class SessionTests(unittest.TestCase):
    def test_zero_documents_is_a_healthy_empty_list(self):
        original = sessions.get_connection
        sessions.get_connection = lambda: EmptyConnection()
        try:
            manager = sessions.SessionManager()
            self.assertEqual(manager.list_documents(), [])
        finally:
            sessions.get_connection = original

    def test_lazy_connection_recovers_after_coreldraw_starts(self):
        connection = EmptyConnection()
        connection.status = type("Disconnected", (), {"connected": False, "last_error": None})()
        connection.connect_calls = 0

        def connect():
            connection.connect_calls += 1
            connection.status.connected = True
            return True

        connection.connect = connect
        original = sessions.get_connection
        sessions.get_connection = lambda: connection
        try:
            sessions.SessionManager()._ensure_connected()
            self.assertEqual(connection.connect_calls, 1)
        finally:
            sessions.get_connection = original

    def manager_for_document(self):
        document = Document()
        connection = DocumentConnection(document)
        manager = sessions.SessionManager()
        fingerprint = sessions._document_fingerprint(document)
        session = manager._register(
            {
                "name": document.FileName,
                "path": sessions._full_path(document),
                "ordinal": 1,
                "fingerprint": fingerprint,
            },
            "edit_active",
        )
        return document, connection, manager, session

    def test_failed_mutation_closes_group_and_calls_undo(self):
        document, connection, manager, session = self.manager_for_document()
        original = sessions.get_connection
        sessions.get_connection = lambda: connection
        try:
            with self.assertRaises(RuntimeError):
                manager.execute(
                    session.session_id,
                    lambda doc: (_ for _ in ()).throw(ValueError("intentional failure")),
                    mutation=True,
                    expected_revision=0,
                )
            self.assertEqual(document.begin_calls, 1)
            self.assertEqual(document.end_calls, 1)
            self.assertEqual(document.undo_calls, 1)
            self.assertEqual(session.revision, 0)
        finally:
            sessions.get_connection = original

    def test_external_document_change_is_rejected(self):
        document, connection, manager, session = self.manager_for_document()
        original = sessions.get_connection
        sessions.get_connection = lambda: connection
        try:
            document.ActivePage.Shapes.values[0].PositionX = 99.0
            with self.assertRaisesRegex(RuntimeError, "changed outside"):
                manager.execute(
                    session.session_id,
                    lambda doc: None,
                    mutation=True,
                    expected_revision=0,
                )
            self.assertEqual(document.begin_calls, 0)
        finally:
            sessions.get_connection = original


if __name__ == "__main__":
    unittest.main()
