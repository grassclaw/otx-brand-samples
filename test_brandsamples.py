import io
import unittest

import brandsamples as bs


class Classify(unittest.TestCase):
    BRAND, OWN = "examplebank", ["examplebank.com"]

    def kind(self, host):
        return bs.classify(host, self.BRAND, self.OWN)

    def test_own_domains_are_excluded(self):
        self.assertIsNone(self.kind("examplebank.com"))
        self.assertIsNone(self.kind("login.examplebank.com"))

    def test_whole_label(self):
        self.assertEqual(self.kind("examplebank.secure-portal.net"), "label")

    def test_affix(self):
        self.assertEqual(self.kind("examplebank-login.top"), "affix")
        self.assertEqual(self.kind("verify-examplebank.xyz"), "affix")

    def test_embedded(self):
        self.assertEqual(self.kind("myexamplebankhelp.com"), "embedded")

    def test_lookalike_after_homoglyph_folding(self):
        self.assertEqual(self.kind("examp1ebank.co"), "lookalike")
        self.assertEqual(self.kind("exarnplebank.co"), "lookalike")

    def test_lookalike_one_edit(self):
        self.assertEqual(self.kind("exampelbank.info"), "lookalike")   # transposition
        self.assertEqual(self.kind("examplebnk.info"), "lookalike")    # omission

    def test_unrelated_host_is_dropped(self):
        self.assertIsNone(self.kind("weather-report.net"))

    def test_short_brands_skip_lookalikes(self):
        self.assertIsNone(bs.classify("abd.com", "abc"))


class Helpers(unittest.TestCase):
    def test_host_of(self):
        self.assertEqual(bs.host_of("https://A.Example.com./x?y=1"), "a.example.com")
        self.assertEqual(bs.host_of("bare.example.org"), "bare.example.org")

    def test_defang(self):
        self.assertEqual(bs.defang("https://a.example.com/x"), "hxxps://a[.]example[.]com/x")

    def test_osa(self):
        self.assertEqual(bs.osa_distance("abcd", "abdc"), 1)
        self.assertEqual(bs.osa_distance("abcd", "abcd"), 0)
        self.assertGreater(bs.osa_distance("abcd", "wxyz", limit=1), 1)


class Collect(unittest.TestCase):
    """The OTX calls run against canned pages, so the paging and dedup are tested offline."""

    def fake_fetch(self, url, key):
        if "/search/pulses" in url:
            if "page=1" in url:
                return {"results": [{"id": "p1", "name": "Bank phishing", "modified": "2026-11-01"}], "next": "more"}
            return {"results": [{"id": "p2", "name": "Lures", "modified": "2026-10-01"}], "next": None}
        if "/pulses/p1/" in url:
            return {"results": [
                {"type": "URL", "indicator": "http://examplebank-login.top/a", "created": "2026-11-01"},
                {"type": "domain", "indicator": "examplebank.com", "created": "2026-11-01"},
                {"type": "FileHash-SHA256", "indicator": "ab" * 32, "created": "2026-11-01"},
            ], "next": None}
        if "/pulses/p2/" in url:
            return {"results": [
                {"type": "hostname", "indicator": "examplebank-login.top", "created": "2026-10-02"},
                {"type": "hostname", "indicator": "examp1ebank.co", "created": "2026-10-02"},
                {"type": "hostname", "indicator": "old.examplebank.net", "created": "2025-01-01"},
            ], "next": None}
        raise AssertionError(url)

    def test_collect(self):
        rows = bs.collect("examplebank", ["examplebank.com"], "k", since="2026-01-01", fetch=self.fake_fetch)
        self.assertEqual([(r["host"], r["kind"]) for r in rows],
                         [("examplebank-login.top", "affix"), ("examp1ebank.co", "lookalike")])

    def test_csv_is_defanged_unless_live(self):
        rows = bs.collect("examplebank", ["examplebank.com"], "k", fetch=self.fake_fetch)
        buf = io.StringIO()
        bs.write_csv(rows, buf)
        self.assertIn("hxxp://examplebank-login[.]top/a", buf.getvalue())
        self.assertNotIn("http://examplebank-login.top", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
