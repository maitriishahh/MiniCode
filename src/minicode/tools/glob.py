def glob(pattern:str, path:str=".", limit:int=50) -> str:
    """
    List files under sandbox whose names match a glob pattern.

    Args:
        pattern: glob pattern, e.g. *.py or test_*
        path: subtree root, relative to the sandbox
        limit: maximum paths to return
    """
