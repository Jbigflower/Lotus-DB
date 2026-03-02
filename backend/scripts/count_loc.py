import os
import argparse
from collections import defaultdict
from typing import List, Tuple


DEFAULT_EXCLUDE_DIRS = [
    ".git", "__pycache__", "venv", "node_modules",
    ".pytest_cache", ".vscode", ".idea"
]

DEFAULT_INCLUDE_EXTS = [".py"]


def norm_ext(ext: str) -> str:
    ext = ext.strip().lower()
    if not ext.startswith("."):
        ext = "." + ext
    return ext


def should_skip_dir(dir_name: str, exclude_dirs: List[str]) -> bool:
    return dir_name in exclude_dirs


def is_line_comment(line: str, ext: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if ext in {".py", ".sh"}:
        return s.startswith("#")
    if ext in {".js", ".ts", ".java", ".c", ".cpp", ".go"}:
        return s.startswith("//")
    if ext in {".css"}:
        # CSS doesn't have single-line comments in standard, but many tools accept //
        return s.startswith("//")
    if ext in {".html"}:
        # Single line HTML comment
        return s.startswith("<!--") and s.endswith("-->")
    return False


def count_file_lines(
    file_path: str,
    ext: str,
    skip_empty: bool,
    skip_comments: bool,
    skip_docstrings: bool
) -> int:
    total = 0
    in_block_comment = False  # For /* ... */ style
    in_html_comment = False   # For <!-- ... --> style
    in_py_docstring = False   # For Python ''' or """ block strings

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for raw_line in f:
                line = raw_line.rstrip("\n")

                stripped = line.strip()
                if skip_empty and stripped == "":
                    continue

                # --- Handle block comments per language ---
                # HTML block comments
                if ext == ".html":
                    if "<!--" in stripped and "-->" in stripped:
                        # open and close on same line → treat as comment if skipping comments
                        if skip_comments:
                            continue
                    elif "<!--" in stripped:
                        in_html_comment = True
                        if skip_comments:
                            continue
                    elif "-->" in stripped and in_html_comment:
                        if skip_comments:
                            in_html_comment = False
                            continue
                        in_html_comment = False

                    if in_html_comment:
                        if skip_comments:
                            continue

                # C-style block comments
                if ext in {".js", ".ts", ".java", ".c", ".cpp", ".go", ".css"}:
                    if "/*" in stripped and "*/" in stripped:
                        # open and close on same line
                        if skip_comments:
                            continue
                    elif "/*" in stripped:
                        in_block_comment = True
                        if skip_comments:
                            continue
                    elif "*/" in stripped and in_block_comment:
                        if skip_comments:
                            in_block_comment = False
                            continue
                        in_block_comment = False

                    if in_block_comment:
                        if skip_comments:
                            continue

                # Python docstrings
                if ext == ".py" and skip_docstrings:
                    quote_count = stripped.count('"""') + stripped.count("'''")
                    if in_py_docstring:
                        # still inside docstring
                        if skip_comments:
                            total += 0  # explicit no-op for clarity
                        # toggle by quote occurrences (handle same-line end)
                        if quote_count > 0:
                            # toggle for each occurrence
                            for _ in range(quote_count):
                                in_py_docstring = not in_py_docstring
                        # if inside and skipping comments
                        if skip_comments:
                            continue
                    else:
                        if quote_count > 0:
                            # enter/exit docstring depending on occurrences
                            for _ in range(quote_count):
                                in_py_docstring = not in_py_docstring
                            # treat this line as comment/docstring if skipping
                            if skip_comments:
                                continue

                # Single-line comments
                if skip_comments and is_line_comment(line, ext):
                    continue

                total += 1
    except (OSError, UnicodeDecodeError):
        # could log or print, but keep silent to avoid noise
        return 0

    return total


def walk_and_count(
    root: str,
    include_exts: List[str],
    exclude_dirs: List[str],
    skip_empty: bool,
    skip_comments: bool,
    skip_docstrings: bool,
    use_relative: bool,
    show_details: bool
) -> Tuple[int, int, dict]:
    files_counted = 0
    ext_totals = defaultdict(int)
    file_details = []  # (path, lines)

    include_exts = [norm_ext(e) for e in include_exts]

    for dirpath, dirnames, filenames in os.walk(root):
        # prune excluded dirs
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d, exclude_dirs)]

        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if include_exts and ext not in include_exts:
                continue

            full_path = os.path.join(dirpath, filename)
            lines = count_file_lines(
                full_path, ext, skip_empty, skip_comments, skip_docstrings
            )

            if lines > 0:
                files_counted += 1
                ext_totals[ext] += lines
                if show_details:
                    path_out = os.path.relpath(full_path, root) if use_relative else full_path
                    file_details.append((path_out, lines))

    total_lines = sum(ext_totals.values())

    if show_details:
        # sort details by lines desc
        file_details.sort(key=lambda x: x[1], reverse=True)

    return files_counted, total_lines, {"by_ext": dict(ext_totals), "details": file_details}


def main():
    parser = argparse.ArgumentParser(
        description="Count lines of code in a project with flexible filters."
    )
    parser.add_argument("--root", default=".", help="Root directory to scan.")
    parser.add_argument(
        "--include-ext",
        nargs="*",
        default=DEFAULT_INCLUDE_EXTS,
        help="File extensions to include (e.g. .py .js). Default: .py"
    )
    parser.add_argument(
        "--exclude-dir",
        nargs="*",
        default=DEFAULT_EXCLUDE_DIRS,
        help="Directory names to exclude. Default common caches and VCS dirs."
    )
    parser.add_argument(
        "--skip-empty",
        action="store_true",
        help="Skip empty lines."
    )
    parser.add_argument(
        "--skip-comments",
        action="store_true",
        help="Skip comment lines."
    )
    parser.add_argument(
        "--skip-docstrings",
        action="store_true",
        help="For Python: skip lines inside triple-quoted docstrings."
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Show per-file line counts."
    )
    parser.add_argument(
        "--relative",
        action="store_true",
        help="When showing details, print paths relative to root."
    )

    args = parser.parse_args()

    root = os.path.abspath(args.root)
    files_counted, total_lines, meta = walk_and_count(
        root=root,
        include_exts=args.include_ext,
        exclude_dirs=args.exclude_dir,
        skip_empty=args.skip_empty,
        skip_comments=args.skip_comments,
        skip_docstrings=args.skip_docstrings,
        use_relative=args.relative,
        show_details=args.details
    )

    print("=== Line Of Code (LOC) Summary ===")
    print(f"Root: {root}")
    print(f"Include extensions: {', '.join([norm_ext(e) for e in args.include_ext])}")
    print(f"Exclude dirs: {', '.join(args.exclude_dir) or '(none)'}")
    print(f"Skip empty: {args.skip_empty}, Skip comments: {args.skip_comments}, Skip docstrings: {args.skip_docstrings}")
    print(f"Files counted: {files_counted}")
    print(f"Total LOC: {total_lines}")
    if meta["by_ext"]:
        print("\nBy extension:")
        for ext, cnt in sorted(meta["by_ext"].items()):
            print(f"  {ext}: {cnt}")

    if args.details and meta["details"]:
        print("\nTop files:")
        for path, cnt in meta["details"][:50]:
            print(f"  {cnt:>8}  {path}")


if __name__ == "__main__":
    main()