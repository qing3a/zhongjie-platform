#!/usr/bin/env python
"""
环境配置检查脚本
检查项目运行所需的环境配置
"""
import os
import sys
from pathlib import Path

def check_python_version():
    """检查 Python 版本 >= 3.10"""
    print("=" * 50)
    print("Python 版本检查")
    version = sys.version_info
    print(f"  当前版本: {version.major}.{version.minor}.{version.micro}")
    if version.major >= 3 and version.minor >= 10:
        print("  [OK] Python 版本满足要求 (>= 3.10)")
        return True
    else:
        print("  [FAIL] Python 版本需要 >= 3.10")
        return False

def check_data_directory():
    """检查 data/ 目录存在"""
    print("=" * 50)
    print("数据目录检查")
    data_dir = Path("data")
    if data_dir.exists() and data_dir.is_dir():
        print(f"  [OK] {data_dir} 目录存在")
        # 检查权限
        if os.access(data_dir, os.W_OK):
            print(f"  [OK] {data_dir} 目录可写")
        else:
            print(f"  [WARN] {data_dir} 目录不可写")
        return True
    else:
        print(f"  [FAIL] {data_dir} 目录不存在，正在创建...")
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            print(f"  [OK] {data_dir} 目录已创建")
            return True
        except Exception as e:
            print(f"  [FAIL] 创建目录失败: {e}")
            return False

def check_env_variables():
    """检查环境变量配置"""
    print("=" * 50)
    print("环境变量检查")
    from dotenv import load_dotenv

    load_dotenv()

    required_vars = {
        "DATA_DIR": "data",
        "LOG_LEVEL": "INFO",
    }

    optional_vars = {
        "PORT": "8000",
        "RATE_LIMIT_MAX": "100",
        "RATE_LIMIT_WINDOW": "60",
        "SQLITE_ENABLED": "false",
        "SQLITE_DB_PATH": "data/mediator.db",
    }

    all_ok = True

    print("\n  必需变量:")
    for var, default in required_vars.items():
        value = os.getenv(var, default)
        print(f"    {var} = {value}")

    print("\n  可选变量 (含默认值):")
    for var, default in optional_vars.items():
        value = os.getenv(var, default)
        print(f"    {var} = {value}")

    # 检查 .env 文件
    env_file = Path(".env")
    if env_file.exists():
        print(f"\n  [OK] .env 文件存在")
    else:
        print(f"\n  [WARN] .env 文件不存在，将使用环境变量默认值")

    return all_ok

def check_dependencies():
    """检查必需的 Python 包"""
    print("=" * 50)
    print("依赖包检查")
    required_packages = [
        "fastapi",
        "uvicorn",
        "pydantic",
        "httpx",
        "dotenv",
    ]

    all_ok = True
    for package in required_packages:
        try:
            __import__(package)
            print(f"  [OK] {package}")
        except ImportError:
            print(f"  [FAIL] {package} 未安装，请运行: pip install {package}")
            all_ok = False

    return all_ok

def main():
    print("\n中介 API 平台 - 环境配置检查")
    print("=" * 50)

    results = []
    results.append(("Python 版本", check_python_version()))
    results.append(("数据目录", check_data_directory()))
    results.append(("环境变量", check_env_variables()))
    results.append(("依赖包", check_dependencies()))

    print("\n" + "=" * 50)
    print("检查结果汇总")
    print("=" * 50)

    all_passed = True
    for name, passed in results:
        status = "[OK]" if passed else "[FAIL]"
        print(f"  {status} {name}")
        if not passed:
            all_passed = False

    print("=" * 50)
    if all_passed:
        print("所有检查通过！可以运行 python start.py 启动服务")
        return 0
    else:
        print("部分检查未通过，请修复后再启动服务")
        return 1

if __name__ == "__main__":
    sys.exit(main())