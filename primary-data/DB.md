# 🔌 БД первичных данных

PostgreSQL в Yandex Cloud. Первичные данные лежат в схеме `primary` — по таблице на
[источник](README.md).

> [!IMPORTANT]
> Пароль в репозиторий **не коммитим** — он лежит в чате команды.
> По админским настройкам и проблемам с доступом — к [@overcoded](https://t.me/overcoded).

## Параметры подключения

| Параметр | Значение |
| --- | --- |
| Host | `rc1b-5l8v7vnu5f1or9d4.mdb.yandexcloud.net` |
| Port | `6432` |
| Database | `106-primary` |
| Schema | `primary` |
| Username | `team-member` |
| Password | *в чате команды* |

## Быстрый старт

<details>
<summary>psql</summary>

```bash
psql "host=rc1b-5l8v7vnu5f1or9d4.mdb.yandexcloud.net \
      port=6432 \
      dbname=106-primary \
      user=team-member \
      sslmode=require"
```

</details>

<details>
<summary>Python (SQLAlchemy + pandas)</summary>

```python
import os

import pandas as pd
from sqlalchemy import create_engine

engine = create_engine(
    "postgresql+psycopg2://team-member:{password}@"
    "rc1b-5l8v7vnu5f1or9d4.mdb.yandexcloud.net:6432/106-primary"
    "?sslmode=require".format(password=os.environ["PRIMARY_DB_PASSWORD"])
)

df = pd.read_sql('select * from "primary".<table> limit 100', engine)
```

</details>
