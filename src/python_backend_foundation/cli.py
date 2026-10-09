"""Portable development server entry point."""

import uvicorn


def main() -> None:
    """Start the application with auto-reload for local development."""
    uvicorn.run(f"{__package__}.main:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
