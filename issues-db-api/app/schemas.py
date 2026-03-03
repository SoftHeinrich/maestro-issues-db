dl_models_collection_schema = {
    "$jsonSchema": {
        "bsonType": "object",
        "additionalProperties": False,
        "required": ["name", "config", "versions", "performances"],
        "properties": {
            "_id": {"bsonType": "objectId", "description": "'_id' must be a objectId"},
            "name": {"bsonType": "string", "description": "'name' must be a string"},
            "config": {
                "bsonType": "object",
                "description": "'config' must be an object",
            },
            "versions": {
                "bsonType": "object",
                "description": "'versions' must be an object",
                "additionalProperties": {
                    "bsonType": "object",
                    "required": ["description"],
                    "properties": {
                        "description": {
                            "bsonType": "string",
                            "description": "'description' must be a string",
                        }
                    },
                },
            },
            "performances": {
                "bsonType": "object",
                "description": "'performances' must be an object",
                "additionalProperties": {
                    "bsonType": "object",
                    "required": ["description"],
                    "properties": {
                        "description": {
                            "bsonType": "string",
                            "description": "'description' must be a string",
                        }
                    },
                },
            },
        },
    }
}

embeddings_collection_schema = {
    "$jsonSchema": {
        "bsonType": "object",
        "additionalProperties": False,
        "properties": {
            "_id": {"bsonType": "objectId", "description": "'_id' must be a objectId"},
            "name": {"bsonType": "string", "description": "'name' must be a string"},
            "config": {
                "bsonType": "object",
                "description": "'config' must be an object",
            },
            "file_id": {
                "bsonType": ["objectId", "null"],
                "description": "'type' must be an objectId",
            },
        },
    }
}

files_collection_schema = {
    "$jsonSchema": {
        "bsonType": "object",
        "additionalProperties": False,
        "properties": {
            "_id": {
                "bsonType": "objectId",
                "description": "'_id' must be a objectId. This is also used as the file id.",
            },
            "description": {
                "bsonType": "string",
                "description": "'description' must be a string",
            },
            "category": {
                "bsonType": "string",
                "description": "'category' must be a string",
            },
        },
    }
}

issue_labels_collection_schema = {
    "$jsonSchema": {
        "bsonType": "object",
        "additionalProperties": False,
        "properties": {
            "_id": {"bsonType": "string", "description": "'_id' must be a string"},
            "existence": {
                "bsonType": ["bool", "null"],
                "description": "'existence' must be a boolean",
            },
            "property": {
                "bsonType": ["bool", "null"],
                "description": "'property' must be a boolean",
            },
            "executive": {
                "bsonType": ["bool", "null"],
                "description": "'executive' must be a boolean",
            },
            "tags": {
                "bsonType": "array",
                "description": "'tags' must be an array of strings",
                "uniqueItems": True,
                "items": {
                    "bsonType": "string",
                    "description": "a 'tag' must be a string",
                },
            },
            "comments": {
                "bsonType": "object",
                "additionalProperties": {
                    "bsonType": "object",
                    "additionalProperties": False,
                    "required": ["author", "comment"],
                    "properties": {
                        "author": {
                            "bsonType": "string",
                            "description": "'author' must be a string",
                        },
                        "comment": {
                            "bsonType": "string",
                            "description": "'comment' must be a string",
                        },
                    },
                },
            },
            "predictions": {
                "bsonType": "object",
                "additionalProperties": {
                    "bsonType": "object",
                    "additionalProperties": {
                        "bsonType": "object",
                        "required": ["prediction", "confidence"],
                        "properties": {
                            "prediction": {
                                "bsonType": "bool",
                                "description": "'prediction' must be a bool",
                            },
                            "confidence": {
                                "bsonType": "double",
                                "description": "'confidence' must be a double",
                            },
                        },
                    },
                },
            },
        },
    }
}


repo_info_collection_schema = {
    "$jsonSchema": {
        "bsonType": "object",
        "additionalProperties": False,
        "properties": {
            "_id": {"bsonType": "string", "description": "'_id' must be a string"},
            "repo_url": {
                "bsonType": "string",
                "description": "'repo_url' must be a string",
            },
            "download_date": {
                "bsonType": ["string", "null"],
                "description": "'download_date' must be a string",
            },
            "batch_size": {
                "bsonType": "int",
                "description": "'batch_size' must be an int",
            },
            "query_wait_time_minutes": {
                "bsonType": "double",
                "description": "'query_wait_time_minutes' must be a double",
            },
            "issue_link_prefix": {
                "bsonType": "string",
                "description": "'issue_link_prefix' must be a string",
            },
        },
    }
}


projects_collection_schema = {
    "$jsonSchema": {
        "bsonType": "object",
        "additionalProperties": False,
        "required": ["ecosystem", "key", "additional_properties"],
        "properties": {
            "_id": {"bsonType": "string", "description": "'_id' must be a string"},
            "ecosystem": {
                "bsonType": "string",
                "description": "'ecosystem' must be a string",
            },
            "key": {"bsonType": "string", "description": "'key' must be a string"},
            "additional_properties": {
                "bsonType": "object",
                "additionalProperties": True,
                "description": "'additional_properties' must be an object",
            },
        },
    }
}


tags_collection_schema = {
    "$jsonSchema": {
        "bsonType": "object",
        "additionalProperties": False,
        "properties": {
            "_id": {"bsonType": "string", "description": "'_id' must be a string"},
            "description": {
                "bsonType": "string",
                "description": "'description' must be a string",
            },
            "type": {"bsonType": "string", "description": "'type' must be a string"},
        },
    }
}

users_collection_schema = {
    "$jsonSchema": {
        "bsonType": "object",
        "additionalProperties": False,
        "properties": {
            "_id": {"bsonType": "string", "description": "'_id' must be a string"},
            "hashed_password": {
                "bsonType": "string",
                "description": "'hashed_password' must be a string",
            },
        },
    }
}
