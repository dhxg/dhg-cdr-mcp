import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from core.operations import apply_operations_raw, inspect_document_raw


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


class Color:
    def __init__(self):
        self.value = None
    def CMYKAssign(self, *value):
        self.value = ("cmyk", *value)
    def RGBAssign(self, *value):
        self.value = ("rgb", *value)


class Fill:
    def __init__(self):
        self.UniformColor = Color()


class Story:
    def __init__(self, value=""):
        self.Text = value
        self.Size = 10
        self.Font = "Arial"
        self.Bold = False


class Text:
    def __init__(self, value=""):
        self.Story = Story(value)
        self.Type = 1
    @property
    def Contents(self):
        return self.Story.Text
    @Contents.setter
    def Contents(self, value):
        self.Story.Text = value


class Layer:
    Name = "Layer 1"
    def __init__(self, page):
        self.page = page
    def CreateRectangle(self, left, bottom, right, top, *radius):
        shape = Shape(len(self.page.Shapes.values) + 1, 1, left, bottom, right-left, top-bottom)
        self.page.Shapes.values.append(shape)
        return shape
    def CreateParagraphText(self, left, top, right, bottom, value):
        shape = Shape(len(self.page.Shapes.values) + 1, 3, left, bottom, right-left, top-bottom)
        shape.Text = Text(value)
        self.page.Shapes.values.append(shape)
        return shape


class Shape:
    def __init__(self, sid, shape_type, x, y, width, height):
        self.StaticID = sid
        self.Type = shape_type
        self.Name = ""
        self.PositionX = x
        self.PositionY = y
        self.SizeWidth = width
        self.SizeHeight = height
        self.Layer = type("ShapeLayer", (), {"Name": "Layer 1"})()
        self.Fill = Fill()
        self.Locked = False
        self.RotationAngle = 0
    def SetSize(self, width, height):
        self.SizeWidth, self.SizeHeight = width, height
    def SetPosition(self, x, y):
        self.PositionX, self.PositionY = x, y
    def Delete(self):
        pass


class Page:
    def __init__(self, index=1):
        self.Index = index
        self.SizeWidth = 210.0
        self.SizeHeight = 297.0
        self.Shapes = Collection([])
        self.ActiveLayer = Layer(self)

    def SetSize(self, width, height):
        self.SizeWidth = float(width)
        self.SizeHeight = float(height)

    def Activate(self):
        pass


class Document:
    def __init__(self):
        self.pages_list = [Page(1)]
        self.ActivePage = self.pages_list[0]
        self.ReferencePoint = 9
        self.FileName = "test.cdr"
        self.FilePath = "C:/Designs"
        self.Modified = False

    @property
    def Pages(self):
        col = Collection(self.pages_list)
        col.Last = self.pages_list[-1]
        return col

    def AddPages(self, count=1):
        for _ in range(count):
            p = Page(len(self.pages_list) + 1)
            self.pages_list.append(p)
            self.ActivePage = p


class OperationTests(unittest.TestCase):
    def test_create_inspect_and_move_top_left(self):
        doc = Document()
        created = apply_operations_raw(doc, [{
            "op": "shape.create_rectangle",
            "name": "hero",
            "bounds": {"x": 10, "y": 20, "width": 30, "height": 40},
        }])
        sid = created[0]["shape_id"]
        inspected = inspect_document_raw(doc)
        self.assertEqual(inspected["shapes"][0]["bounds"], {"x": 10.0, "y": 20.0, "width": 30.0, "height": 40.0})
        apply_operations_raw(doc, [{"op": "shape.move", "shape_id": sid, "x": 15, "y": 25}])
        moved = inspect_document_raw(doc)["shapes"][0]["bounds"]
        self.assertEqual((moved["x"], moved["y"]), (15.0, 25.0))

    def test_text_is_editable(self):
        doc = Document()
        result = apply_operations_raw(doc, [{
            "op": "text.create_frame",
            "name": "heading",
            "text": "Old",
            "bounds": {"x": 10, "y": 10, "width": 100, "height": 20},
        }])
        sid = result[0]["shape_id"]
        apply_operations_raw(doc, [{"op": "text.set_content", "shape_id": sid, "value": "New"}])
        self.assertEqual(inspect_document_raw(doc)["shapes"][0]["text"], "New")

    def test_operations_do_not_resolve_shapes_from_another_page(self):
        doc = Document()
        second_page = Page(2)
        other = Shape(99, 1, 0, 0, 10, 10)
        other.Name = "other-page"
        second_page.Shapes.values.append(other)
        doc.pages_list.append(second_page)
        with self.assertRaisesRegex(ValueError, "active page"):
            apply_operations_raw(doc, [{"op": "shape.move", "shape_id": "99", "x": 5, "y": 5}])

    def test_ambiguous_names_are_rejected(self):
        doc = Document()
        first = Shape(1, 1, 0, 0, 10, 10)
        second = Shape(2, 1, 20, 0, 10, 10)
        first.Name = second.Name = "duplicate"
        doc.ActivePage.Shapes.values.extend([first, second])
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            apply_operations_raw(doc, [{"op": "shape.move", "shape_id": "duplicate", "x": 5, "y": 5}])

    def test_append_page_operation(self):
        doc = Document()
        res = apply_operations_raw(doc, [{
            "op": "append_page",
            "width_mm": 210,
            "height_mm": 297,
        }])
        self.assertEqual(res[0]["op"], "append_page")
        self.assertEqual(res[0]["page_index"], 2)
        self.assertEqual(res[0]["total_pages"], 2)
        self.assertEqual(res[0]["width_mm"], 210.0)
        self.assertEqual(res[0]["height_mm"], 297.0)


if __name__ == "__main__":
    unittest.main()

