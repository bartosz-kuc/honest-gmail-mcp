"""Tests for _build_mime: headers and attachments with non-ASCII text must stay valid RFC 5322.

Run: python -m unittest discover -s tests
"""
import base64
import os
import sys
import tempfile
import unittest
from email import policy
from email.parser import BytesParser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server  # noqa: E402


def parse(message):
    raw = base64.urlsafe_b64decode(message["raw"])
    return raw, BytesParser(policy=policy.default).parsebytes(raw)


class BuildMimeTest(unittest.TestCase):
    def test_non_ascii_display_name_keeps_address_readable(self):
        raw, msg = parse(server._build_mime('"Żółć Gęślą" <jan.kowalski@example.com>', "Re: Faktura", "Cześć"))
        addr = msg["To"].addresses[0]
        self.assertEqual(addr.addr_spec, "jan.kowalski@example.com")
        self.assertEqual(addr.display_name, "Żółć Gęślą")
        to_line = next(l for l in raw.split(b"\r\n") + raw.split(b"\n") if l.lower().startswith(b"to:"))
        self.assertIn(b"<jan.kowalski@example.com>", to_line)  # the address itself is never encoded

    def test_non_ascii_attachment_name_and_type(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "Formatka — Łódź.xlsx")
            data = b"PK\x03\x04 test bytes"
            with open(path, "wb") as f:
                f.write(data)
            _, msg = parse(server._build_mime("a@example.com", "Załącznik", "Treść ąę", attachments=[path]))
        parts = list(msg.iter_attachments())
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0].get_filename(), "Formatka — Łódź.xlsx")
        self.assertEqual(parts[0].get_content_type(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertEqual(parts[0].get_content(), data)
        self.assertEqual(msg.get_body(("plain",)).get_content().strip(), "Treść ąę")
        self.assertEqual(msg["Subject"], "Załącznik")

    def test_unknown_extension_falls_back_to_octet_stream(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "plik.nieznany123")
            with open(path, "wb") as f:
                f.write(b"x")
            _, msg = parse(server._build_mime("a@example.com", "s", "b", attachments=[path]))
        self.assertEqual(next(msg.iter_attachments()).get_content_type(), "application/octet-stream")

    def test_reply_headers_cc_bcc(self):
        _, msg = parse(server._build_mime(
            "a@example.com", "Re: Temat", "b", cc="c@example.com", bcc="d@example.com",
            extra_headers={"In-Reply-To": "<id1@example.com>", "References": "<id0@example.com> <id1@example.com>"},
        ))
        self.assertEqual(msg["In-Reply-To"], "<id1@example.com>")
        self.assertEqual(msg["References"], "<id0@example.com> <id1@example.com>")
        self.assertEqual(msg["Cc"], "c@example.com")
        self.assertEqual(msg["Bcc"], "d@example.com")

    def test_plain_message_without_attachments(self):
        _, msg = parse(server._build_mime("a@example.com", "Prośba", "Dzień dobry"))
        self.assertEqual(msg.get_content_type(), "text/plain")
        self.assertEqual(msg.get_content().strip(), "Dzień dobry")
        self.assertEqual(msg["Subject"], "Prośba")


if __name__ == "__main__":
    unittest.main()
