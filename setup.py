from setuptools import setup, find_packages

setup(
    name="llm-bridge",
    version="1.0.0",
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'bridge=bridge.main:main',
        ],
    },
    install_requires=[
        'fastapi==0.109.0',
        'uvicorn==0.27.0',
        'aiohttp==3.9.1',
        'python-dotenv==1.0.0',
        'tiktoken==0.6.0',
        'jinja2==3.1.3',
    ],
    author="LLM Bridge Contributors",
    description="A bridge service for LLM API proxying",
    long_description=open('README.md').read(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/llm-bridge",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
)
