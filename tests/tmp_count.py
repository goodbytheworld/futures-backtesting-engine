import os

root = r"C:\Users\Dans Rozenberg\Downloads\single_asset_backtester_private-main"

excl_dirs = {'.git', '__pycache__', 'venv', '.venv', 'data', 'results', 'logs', 'cache', '.vscode', '.idea', 'market_data', 'history', '.pytest_cache'}
incl_exts = {'.py', '.md', '.txt', '.yaml', '.yml', '.json', '.toml', '.ini'}

lines = 0
files = 0
dirs = 0

for dp, dn, fn in os.walk(root):
    # filter in-place to avoid recursion into excl_dirs
    dn[:] = [d for d in dn if d not in excl_dirs and not d.startswith('.')]
    dirs += 1
    for f in fn:
        if os.path.splitext(f)[1] in incl_exts:
            files += 1
            filepath = os.path.join(dp, f)
            try:
                with open(filepath, 'r', encoding='utf-8') as file:
                    lines += sum(1 for _ in file)
            except Exception:
                pass

print(f"Папки: {dirs}")
print(f"Файлы: {files}")
print(f"Строки кода: {lines}")
