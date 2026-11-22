# Liest APP_VERSION aus wallura.py (für build_installer.bat)
import pathlib
import re

src = pathlib.Path(__file__).with_name("wallura.py").read_text(encoding="utf-8")
print(re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', src, re.M).group(1))
