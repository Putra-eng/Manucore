from pymongo import MongoClient

client = MongoClient("mongodb+srv://manucore:banggajadianakpolman@workordermanagement.pzqc53x.mongodb.net/")
db = client["manucore_db"]

clients_collection = db["client"]
users_collection = db["staff_users"]
requests_collection = db["requests"]
