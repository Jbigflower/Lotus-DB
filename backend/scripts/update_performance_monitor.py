import ast
import os
from pathlib import Path


def refactor_performance_decorators(file_path):
    """
    重构指定文件中性能监控装饰器的使用：
    1. 将异步函数/方法的 @performance_monitor 替换为
    2. 将同步函数/方法的 @performance_monitor 替换为
    3. 更新对应的导入语句
    """
    with open(file_path, "r", encoding="utf-8") as f:
        code = f.read()

    tree = ast.parse(code)
    modified = False

    # 处理导入语句
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "config.logging":
            # 查找包含 performance_monitor 的导入
            for alias in node.names:
                if alias.name == "performance_monitor":
                    # 替换为两个新装饰器的导入
                    node.names.remove(alias)
                    node.names.extend(
                        [
                            ast.alias(name="performance_monitor_async", asname=None),
                            ast.alias(name="performance_monitor_sync", asname=None),
                        ]
                    )
                    modified = True
            # 清理空导入
            if not node.names:
                tree.body.remove(node)

    # 处理装饰器替换
    for node in ast.walk(tree):
        # 处理函数定义（包括异步）
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for i, decorator in enumerate(node.decorator_list):
                # 检查是否是 performance_monitor 装饰器
                if (
                    isinstance(decorator, ast.Name)
                    and decorator.id == "performance_monitor"
                ):
                    # 根据函数类型替换装饰器名称
                    new_decorator = (
                        "performance_monitor_async"
                        if isinstance(node, ast.AsyncFunctionDef)
                        else "performance_monitor_sync"
                    )
                    node.decorator_list[i] = ast.Name(id=new_decorator, ctx=ast.Load())
                    modified = True
                # 处理带参数的装饰器情况（如 @performance_monitor(...)）
                elif (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Name)
                    and decorator.func.id == "performance_monitor"
                ):
                    new_decorator = (
                        "performance_monitor_async"
                        if isinstance(node, ast.AsyncFunctionDef)
                        else "performance_monitor_sync"
                    )
                    decorator.func = ast.Name(id=new_decorator, ctx=ast.Load())
                    modified = True

    if modified:
        # 生成修改后的代码
        new_code = ast.unparse(tree)
        # 保存修改
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_code)
        print(f"已更新文件: {file_path}")
    else:
        print(f"文件无需修改: {file_path}")


def batch_refactor_performance_decorators(root_dir):
    """批量处理目录下所有 Python 文件"""
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith(".py"):
                file_path = Path(dirpath) / filename
                refactor_performance_decorators(file_path)


if __name__ == "__main__":
    # 替换当前目录下所有 Python 文件
    batch_refactor_performance_decorators(".")
