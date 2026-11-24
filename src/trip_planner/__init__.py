import sys
from importlib.util import find_spec
from pathlib import Path


def main() -> None:
    app = find_spec("streamlit_app")
    if app is None or app.origin is None:
        raise RuntimeError("MakeMyJourney's Streamlit entry point is not installed.")

    from streamlit.web import cli

    sys.argv = ["streamlit", "run", str(Path(app.origin).resolve())]
    cli.main()
