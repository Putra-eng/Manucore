from pymongo import MongoClient

client = MongoClient("mongodb+srv://manucore:banggajadianakpolman@workordermanagement.pzqc53x.mongodb.net/")
db = client["manucore_db"]


staff_users_collection    = db["staff_users"]       
clients_collection        = db["client"]            
requests_collection       = db["requests"]          
production_orders_collection = db["production_orders"]  
production_log_collection = db["production_log"]     
reject_log_collection     = db["reject_log"]        