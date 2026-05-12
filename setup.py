"""author_agent 安装脚本"""
from setuptools import setup, find_packages

setup(
    name="author-agent",
    version="0.1.0",
    description="名称规范记录智能体",
    packages=find_packages(include=["author_agent","author_agent.*"]),
    python_requires=">=3.9",
    install_requires=["pandas>=1.3","openpyxl>=3.0","flask>=3.0","waitress>=3.0"],
)
