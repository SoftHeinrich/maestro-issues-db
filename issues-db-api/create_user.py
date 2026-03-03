import string 

from passlib.context import CryptContext
from pymongo import MongoClient

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

mongo_client = MongoClient("mongodb://localhost:27017")
users_collection = mongo_client["Users"]["Users"]

def prompt(p):
    while True:
        response = input(p)
        if not response:
            print('E: Value cannot be empty.')
            continue
        if not set(response).issubset(set(string.ascii_letters)):
            print('E: Value may only contain ascii letters and/or numbers.')
            continue
        return response  

username = prompt('Username: ')
password = prompt('Password: ')

users_collection.insert_one(
    {
        "_id": username,
        "hashed_password": pwd_context.hash(password),
    }
)