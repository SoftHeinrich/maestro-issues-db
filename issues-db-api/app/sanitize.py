def sanitize_mongo_filter(filter_dict: dict) -> dict:
    """Strip dangerous MongoDB operators from user-supplied filter dicts."""
    ALLOWED_OPERATORS = {
        "$and", "$or", "$not", "$nor",
        "$eq", "$ne", "$in", "$nin",
        "$gt", "$gte", "$lt", "$lte",
        "$exists", "$regex", "$elemMatch",
    }
    def _clean(obj):
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()
                    if not k.startswith("$") or k in ALLOWED_OPERATORS}
        elif isinstance(obj, list):
            return [_clean(item) for item in obj]
        return obj
    return _clean(filter_dict)
