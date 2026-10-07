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
<summary>~/.pgpass — чтобы не вводить пароль каждый раз</summary>

`psql` (используется в некоторых лоадерах первичных данных) - берет пароль подключения к БД из ~/.pgpass:

```bash
umask 077
echo 'rc1b-5l8v7vnu5f1or9d4.mdb.yandexcloud.net:6432:106-primary:team-member:ПАРОЛЬ' >> ~/.pgpass
chmod 600 ~/.pgpass
```

Двоеточие и обратный слэш внутри пароля нужно экранировать обратным слэшем:
`a:b` записывается как `a\:b`. 

</details>

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
import pandas as pd
from sqlalchemy import create_engine

# Пароль берётся из ~/.pgpass (или из PGPASSWORD) — так же, как psql.
engine = create_engine(
    "postgresql+psycopg2://team-member@"
    "rc1b-5l8v7vnu5f1or9d4.mdb.yandexcloud.net:6432/106-primary"
    "?sslmode=require"
)

df = pd.read_sql('select * from "primary".<table> limit 100', engine)
```

</details>
