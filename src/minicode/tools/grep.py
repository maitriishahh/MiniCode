def grep(pattern: str, path:str=".", include:str="*",limit:int=50) -> str:
    """
    Search file contents under the sandbox for a regex pattern.

    Args:
        pattern: Regex pattern to search for
        path: Subtree root, relative to the sandbox
        include: Only search files whose names match this glob, e.g. *.py
        limit: Maximum matches to return
    """

