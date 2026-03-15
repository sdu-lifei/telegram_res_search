from setuptools import setup, find_packages

setup(
    name="pansou_py",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "fastapi",
        "uvicorn",
        "pydantic",
        "pydantic-settings",
        "httpx",
        "sqlalchemy",
        "aiosqlite",
        "beautifulsoup4",
        "lxml",
        "aiohttp",
    ],
)
