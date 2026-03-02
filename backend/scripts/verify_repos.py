#!/usr/bin/env python3
"""
验证仓储层实现的完整性和一致性
"""

import os
import ast
import sys
from pathlib import Path


def analyze_repo_file(file_path):
    """分析仓储文件的结构"""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        return {"error": f"语法错误: {e}"}

    info = {
        "file": file_path.name,
        "classes": [],
        "imports": [],
        "methods": [],
        "docstring": None,
    }

    # 获取模块文档字符串
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
    ):
        info["docstring"] = tree.body[0].value.value

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_info = {
                "name": node.name,
                "bases": [ast.unparse(base) for base in node.bases],
                "methods": [],
                "docstring": ast.get_docstring(node),
            }

            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    class_info["methods"].append(item.name)

            info["classes"].append(class_info)

        elif isinstance(node, ast.Import):
            for alias in node.names:
                info["imports"].append(alias.name)

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                info["imports"].append(f"{module}.{alias.name}")

    return info


def main():
    """主函数"""
    repo_dir = Path("src/repos/mongo_repos")

    if not repo_dir.exists():
        print(f"错误: 目录 {repo_dir} 不存在")
        return 1

    print("=" * 60)
    print("MongoDB 仓储层实现验证报告")
    print("=" * 60)

    repo_files = list(repo_dir.glob("*_repo.py"))
    repo_files.append(repo_dir / "base_repo.py")

    all_repos = []
    errors = []

    for file_path in sorted(repo_files):
        if not file_path.exists():
            continue

        print(f"\n📁 分析文件: {file_path.name}")
        print("-" * 40)

        info = analyze_repo_file(file_path)

        if "error" in info:
            errors.append(f"{file_path.name}: {info['error']}")
            print(f"❌ {info['error']}")
            continue

        all_repos.append(info)

        # 显示基本信息
        if info["docstring"]:
            print(f"📝 文档: {info['docstring'][:100]}...")

        # 显示类信息
        for class_info in info["classes"]:
            print(f"🏗️  类名: {class_info['name']}")
            if class_info["bases"]:
                print(f"   继承: {', '.join(class_info['bases'])}")
            if class_info["docstring"]:
                print(f"   文档: {class_info['docstring'][:80]}...")
            print(f"   方法数: {len(class_info['methods'])}")

            # 显示关键方法
            key_methods = [
                m
                for m in class_info["methods"]
                if m.startswith(
                    ("find_", "create_", "update_", "delete_", "search_", "get_")
                )
            ]
            if key_methods:
                print(
                    f"   关键方法: {', '.join(key_methods[:5])}{'...' if len(key_methods) > 5 else ''}"
                )

    # 统计信息
    print("\n" + "=" * 60)
    print("📊 统计信息")
    print("=" * 60)

    total_files = len(all_repos)
    total_classes = sum(len(repo["classes"]) for repo in all_repos)
    total_methods = sum(
        len(method)
        for repo in all_repos
        for class_info in repo["classes"]
        for method in [class_info["methods"]]
    )

    print(f"✅ 总文件数: {total_files}")
    print(f"✅ 总类数: {total_classes}")
    print(f"✅ 总方法数: {total_methods}")

    if errors:
        print(f"❌ 错误数: {len(errors)}")
        for error in errors:
            print(f"   - {error}")

    # 验证仓储类命名规范
    print("\n📋 仓储类验证")
    print("-" * 40)

    expected_repos = [
        "BaseRepo",
        "MovieRepo",
        "AssetRepo",
        "LibraryRepo",
        "UserRepo",
        "UserAssetRepo",
        "WatchHistoryRepo",
        "TaskRepo",
        "LogRepo",
    ]

    found_repos = []
    for repo in all_repos:
        for class_info in repo["classes"]:
            if class_info["name"].endswith("Repo"):
                found_repos.append(class_info["name"])

    missing_repos = set(expected_repos) - set(found_repos)
    extra_repos = set(found_repos) - set(expected_repos)

    print(f"✅ 已实现仓储: {', '.join(sorted(found_repos))}")

    if missing_repos:
        print(f"❌ 缺失仓储: {', '.join(sorted(missing_repos))}")

    if extra_repos:
        print(f"ℹ️  额外仓储: {', '.join(sorted(extra_repos))}")

    # 验证继承关系
    print("\n🔗 继承关系验证")
    print("-" * 40)

    base_repo_found = False
    inheritance_correct = True

    for repo in all_repos:
        for class_info in repo["classes"]:
            if class_info["name"] == "BaseRepo":
                base_repo_found = True
                print(f"✅ 基础仓储类: {class_info['name']}")
            elif class_info["name"].endswith("Repo"):
                if any("BaseRepo" in base for base in class_info["bases"]):
                    print(f"✅ {class_info['name']} -> BaseRepo")
                else:
                    print(f"❌ {class_info['name']} 未继承 BaseRepo")
                    inheritance_correct = False

    if not base_repo_found:
        print("❌ 未找到 BaseRepo 基础类")
        inheritance_correct = False

    # 最终结果
    print("\n" + "=" * 60)
    print("🎯 验证结果")
    print("=" * 60)

    if errors:
        print("❌ 验证失败: 存在语法错误")
        return 1
    elif not inheritance_correct:
        print("⚠️  验证警告: 继承关系不正确")
        return 1
    elif missing_repos:
        print("⚠️  验证警告: 存在缺失的仓储类")
        return 1
    else:
        print("✅ 验证通过: 所有仓储类实现完整且结构正确")
        return 0


if __name__ == "__main__":
    sys.exit(main())
