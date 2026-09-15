from app.main import app
from app.config import config

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=config.port, reload=True)
