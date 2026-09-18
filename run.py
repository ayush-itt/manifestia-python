from app.config import config
from app.logging_setup import setup_logging

setup_logging(config.log_level)

from app.main import app  # noqa: E402

if __name__ == "__main__":
    import uvicorn

    ssl_files = config.resolved_ssl_files()
    ssl_kwargs = {}
    if ssl_files:
        ssl_kwargs["ssl_certfile"] = str(ssl_files[0])
        ssl_kwargs["ssl_keyfile"] = str(ssl_files[1])

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=config.port,
        reload=True,
        **ssl_kwargs,
    )
