import json
import os

db_type='postgresql+psycopg2',
POSTGRESQL_INFO = dict(
    db_name="Cloud_user_system", # local-test
    # db_name="cloud_user_system",
    user="postgres",
    password="qiu560022",
    host="localhost",
    port="5432",
)
connection_info = 'postgresql+psycopg2://{user}:{password}@{host}:{port}/{db_name}'
db_url = connection_info.format(**POSTGRESQL_INFO)


class ProductionConfig():
    SECRET_KEY = "aK2UxC9p"
    DEBUG = True

    SQLALCHEMY_DATABASE_URI = db_url
