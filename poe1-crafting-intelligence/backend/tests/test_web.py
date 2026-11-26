import shutil
import subprocess
from pathlib import Path

import pytest

PAGE = Path(__file__).parents[1] / "poeci" / "web" / "index.html"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_page_script_has_no_syntax_error(tmp_path):
    # Regression: a broken regex in the page script stopped every tab from working.
    html = PAGE.read_text(encoding="utf-8")
    js = tmp_path / "page.js"
    js.write_text(html[html.index("<script>") + 8:html.rindex("</script>")], encoding="utf-8")
    r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_no_hidden_control_characters_in_code():
    # Regression: an inserted "\b" became a backspace character and silently broke a regex.
    root = Path(__file__).parents[1] / "poeci"
    for f in list(root.rglob("*.py")) + list(root.rglob("*.html")):
        text = f.read_text(encoding="utf-8")
        assert not [c for c in text if ord(c) < 32 and c not in "\n\r\t"], f
