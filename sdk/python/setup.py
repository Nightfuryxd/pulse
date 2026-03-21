from setuptools import setup, find_packages

setup(
    name="pulse-sdk",
    version="1.0.0",
    description="PULSE Infrastructure Intelligence SDK for Python",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[],   # zero required deps — uses stdlib urllib as fallback
    extras_require={
        "full": ["httpx>=0.20", "sqlalchemy>=1.4"],
    },
)
