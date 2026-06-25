"""PyInstaller runtime hook: point NLTK at the bundled punkt_tab data.

The release build bundles the punkt_tab tokenizer model under
``<bundle>/nltk_data`` (see ``packaging/tta.spec`` --add-data). NLTK only
looks at directories on ``nltk.data.path``; in a frozen --onefile binary
``sys._MEIPASS`` is the temporary extraction root. We prepend the bundled
path so ``mod_tokenize`` resolves the model fully offline, with no download
(ADR-0014, QA-PRIV).
"""

import os
import sys

_meipass = getattr(sys, "_MEIPASS", None)
if _meipass:
    _bundled = os.path.join(_meipass, "nltk_data")
    # Honour NLTK's documented override and the in-process search path so it
    # works whether nltk is imported before or after this hook runs.
    os.environ["NLTK_DATA"] = _bundled
    try:
        import nltk.data

        if _bundled not in nltk.data.path:
            nltk.data.path.insert(0, _bundled)
    except Exception:
        # nltk not imported yet: NLTK_DATA env var still steers it on import.
        pass
