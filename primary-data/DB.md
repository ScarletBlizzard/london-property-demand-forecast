# 🔌 БД первичных данных

PostgreSQL на серваке @overcoded (уехали на него после потери ЦОДа в Я.Клауде). Первичные данные лежат в схеме `primary` — по таблице на
[источник](README.md).

> [!IMPORTANT]
> Пароль в репозиторий **не коммитим** — он лежит в чате команды.
> По админским настройкам и проблемам с доступом — к [@overcoded](https://t.me/overcoded).

## Параметры подключения

| Параметр | Значение |
| --- | --- |
| Host | `212.26.253.190` |
| Port | `48723` |
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
echo '212.26.253.190:48723:106-primary:team-member:ПАРОЛЬ' >> ~/.pgpass
chmod 600 ~/.pgpass
```

Двоеточие и обратный слэш внутри пароля нужно экранировать обратным слэшем:
`a:b` записывается как `a\:b`. 

</details>

<details>
<summary>psql</summary>

```bash
psql "host=212.26.253.190 \
      port=48723 \
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
    "212.26.253.190:48723/106-primary"
    "?sslmode=require"
)

df = pd.read_sql('select * from "primary".<table> limit 100', engine)
```

</details>
