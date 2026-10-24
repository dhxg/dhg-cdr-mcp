import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1] / "server"
sys.path.insert(0, str(SERVER_DIR))

from tools.search import _filter_candidates, decode_objurl


class ObjUrlDecodeTests(unittest.TestCase):
    def test_decode_known_sample(self):
        encoded = (
            "ipprf_z2C$qAzdH3FAzdH3Fox9_z&e3Bftgwt42_z&e3BvgAzdH3Fsw62j"
            "AzdH3FaabIQfetsy8tabvria68t3na6f"
        )
        self.assertEqual(
            decode_objurl(encoded),
            "https://wx4.sinaimg.cn/large/008IQsvily1i08cph0r1ij30rs",
        )

    def test_decode_https_prefix(self):
        # "ipprf" 前缀本身就是编码：i→h,p→t,p→t,r→p,f→s = https
        self.assertTrue(decode_objurl(
            "ipprf_z2C$qAzdH3FAzdH3Frtvfm_z&e3Bkwt17_z&e3Bv54AzdH3Fujj1"
            "AzdH3Fbnadcwwuw9au9kukw0m0mmkb0m"
        ).startswith("https://pics6.baidu.com/feed/"))

    def test_non_ipprf_returns_unchanged(self):
        self.assertEqual(decode_objurl("https://a.com/x.jpg"),
                         "https://a.com/x.jpg")


class FilterCandidateTests(unittest.TestCase):
    def _cand(self, url="https://ok.com/a.jpg", w=2000, h=1000,
              clarity=80, type_="jpg"):
        return {"url": url, "width": w, "height": h, "clarity": clarity,
                "type": type_, "host": url.split("//")[1].split("/")[0]}

    def test_removes_denylist_hosts(self):
        cands = [
            self._cand(url="https://img.nipic.com/a.jpg"),
            self._cand(url="https://img.ok.com/b.jpg"),
            self._cand(url="https://s.699pic.com/c.jpg"),
        ]
        out = _filter_candidates(cands, 1000)
        self.assertEqual([c["host"] for c in out], ["img.ok.com"])

    def test_removes_gif_and_small_images(self):
        cands = [
            self._cand(url="https://ok.com/a.gif", type_="gif"),
            self._cand(w=800, h=600),
            self._cand(w=2000, h=1000),
        ]
        out = _filter_candidates(cands, 1000)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["width"], 2000)

    def test_keeps_order_of_survivors(self):
        cands = [
            self._cand(url="https://ok.com/a.jpg"),
            self._cand(url="https://ok.com/b.jpg", w=900, h=900),
            self._cand(url="https://ok.com/c.jpg", clarity=90),
        ]
        out = _filter_candidates(cands, 1000)
        self.assertEqual([c["url"] for c in out],
                         ["https://ok.com/a.jpg", "https://ok.com/c.jpg"])


if __name__ == "__main__":
    unittest.main()
