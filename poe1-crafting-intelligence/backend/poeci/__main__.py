"""`python -m poeci` starts the local server on http://127.0.0.1:8765"""
import os

import uvicorn


def main() -> None:
    from .api.app import create_app

    host = os.environ.get("POECI_HOST", "127.0.0.1")  # local only by default
    port = int(os.environ.get("POECI_PORT", "8765"))
    print(f"PoE1 Crafting Intelligence running at http://{host}:{port}  (Ctrl+C to stop)")
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
