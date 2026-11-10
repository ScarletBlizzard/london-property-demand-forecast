# 🔌 БД первичных данных

PostgreSQL на серваке @overcoded (уехали на него после потери ЦОДа в Я.Клауде). Первичные данные лежат в схеме `primary` — по таблице на
[источник](README.md).

> [!IMPORTANT]
> Пароль в репозиторий **не коммитим** — он лежит в чате команды.
> По админским настройкам и проблемам с доступом — к [@overcoded](https://t.me/overcoded).

## Параметры подключения

Хост, порт, база и пользователь (`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGSSLMODE`) лежат в одном месте — [db.env](db.env).
Его подключают все лоадеры (`source ../../db.env`), при смене сервера правим только его. Пароль — в чате команды.

Чтобы примеры ниже работали, загрузите параметры в текущую оболочку (из корня `primary-data/`):

```bash
source db.env
```

## Быстрый старт

<details>
<summary>~/.pgpass — чтобы не вводить пароль каждый раз</summary>

`psql` (используется в некоторых лоадерах первичных данных) - берет пароль подключения к БД из ~/.pgpass:

```bash
source db.env
umask 077
echo "$PGHOST:$PGPORT:$PGDATABASE:$PGUSER:ПАРОЛЬ" >> ~/.pgpass
chmod 600 ~/.pgpass
```

Двоеточие и обратный слэш внутри пароля нужно экранировать обратным слэшем:
`a:b` записывается как `a\:b`.

</details>

<details>
<summary>psql</summary>

`psql` сам читает `PG*` из окружения:

```bash
source db.env
psql
```

</details>

<details>
<summary>Python (SQLAlchemy + pandas)</summary>

Запускайте из оболочки, где выполнен `source db.env`: драйвер (libpq) берёт хост, порт, базу и пользователя
из `PG*`, а пароль — из ~/.pgpass (или `PGPASSWORD`), так же, как `psql`.

```python
import pandas as pd
from sqlalchemy import create_engine

engine = create_engine("postgresql+psycopg2://")

df = pd.read_sql('select * from "primary".<table> limit 100', engine)
```

</details>
