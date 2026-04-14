# Maestro Issues Database (API)

This repository contains the issues database and its API of Maestro. It is part of the [Maestro project](../Maestro/README.md).

The Mongo archives can be downloaded from [Zenodo](https://zenodo.org/record/8372644). Note that this version also contains a lite variant of the MiningDesignDecisions archive. This lite variant only contains the best trained model (BERT) and no other files or embeddings.

## Setup

### Prerequisites

- Docker and Docker Compose
- The `maestro_traefik` Docker network must exist (created by the main Maestro setup)

### Quick Start

```bash
cd maestro-project/maestro-issues-db/
```

Generate your API secret key:

```bash
openssl rand -hex 32
```

Create the config file:

```bash
nano issues-db-api/app/config.py
```

Add the following content:

```python
SECRET_KEY = 'SECRET_FROM_OPENSSL'
```

Start the services:

```bash
docker compose up --build -d
```

This starts:

| Service | Port | Description |
|---------|------|-------------|
| MongoDB | 27017 | Document database |
| PostgreSQL | 5432 | Relational database (pinned to v16) |
| Mongo Express | 8081 | MongoDB web admin |
| Issues DB API | 8000 | FastAPI backend |
| Backup | -- | Automated backup service |

### Import Data

Download the archives from [Zenodo](https://zenodo.org/record/8372644) and restore them:

**JiraRepos:**

```bash
docker cp ./mongodump-JiraRepos_2023-03-07-16:00.archive mongo:/mongodump-JiraRepos.archive
docker exec -i mongo mongorestore --gzip --archive=mongodump-JiraRepos.archive --nsFrom "JiraRepos.*" --nsTo "JiraRepos.*"
```

**MiningDesignDecisions (lite, recommended):**

```bash
docker cp ./mongodump-MiningDesignDecisions-lite.archive mongo:/mongodump-MiningDesignDecisions-lite.archive
docker exec -i mongo mongorestore --gzip --archive=mongodump-MiningDesignDecisions-lite.archive --nsFrom "MiningDesignDecisions.*" --nsTo "MiningDesignDecisions.*"
```

**MiningDesignDecisions (full):**

```bash
docker cp ./mongodump-MiningDesignDecisions.archive mongo:/mongodump-MiningDesignDecisions.archive
docker exec -i mongo mongorestore --gzip --archive=mongodump-MiningDesignDecisions.archive --nsFrom "MiningDesignDecisions.*" --nsTo "MiningDesignDecisions.*"
```

> **Tip**: For large imports, if MongoDB runs out of memory, limit the WiredTiger cache
> by adding to the mongo service in `docker-compose.yml`:
> ```yaml
> command: ["mongod", "--wiredTigerCacheSizeGB", "2"]
> ```
> To import only a specific collection:
> ```bash
> docker exec -i mongo mongorestore --gzip --archive=mongodump-JiraRepos.archive --nsInclude="JiraRepos.Apache"
> ```

### Create First User

The first user must be inserted directly into MongoDB (the API's `/create-account` endpoint requires authentication):

```bash
docker exec issues-db-api python3 -c "
import bcrypt
from pymongo import MongoClient
hashed = bcrypt.hashpw(b'YOUR_PASSWORD', bcrypt.gensalt()).decode()
client = MongoClient('mongodb://mongo:27017')
client['Users']['Users'].insert_one({'_id': 'YOUR_USERNAME', 'hashed_password': hashed})
print('User created')
"
```

After this, additional users can be added via the API's `/create-account` endpoint.

### Dump Data (Optional)

```bash
# Dump JiraRepos
docker exec -i mongo mongodump --db=JiraRepos --gzip --archive=mongodump-JiraRepos.archive
docker cp mongo:mongodump-JiraRepos.archive ./mongodump-JiraRepos.archive

# Dump MiningDesignDecisions
docker exec -i mongo mongodump --db=MiningDesignDecisions --gzip --archive=mongodump-MiningDesignDecisions.archive
docker cp mongo:mongodump-MiningDesignDecisions.archive ./mongodump-MiningDesignDecisions.archive
```

### Known Issues

- **passlib/bcrypt incompatibility**: passlib 1.7.4 + bcrypt 5.x crashes. `bcrypt==4.1.3` is pinned in `issues-db-api/requirements.txt`.
- **PostgreSQL version**: Pinned to `postgres:17`. Version 18+ changed data directory format.

## API Documentation

The API is documented via OpenAPI. Once running, access the interactive docs at `http://localhost:8000/docs` or see the [usage documentation](../Maestro/docs/usage/issues_db_api/README.md).

## References

<a id="montgomery_alternative_2022">[1]</a> Montgomery, L., Luders, C., & Maalej, W. (2022, May). An alternative issue tracking dataset of public jira repositories. In Proceedings of the 19th International Conference on Mining Software Repositories (pp. 73-77).
