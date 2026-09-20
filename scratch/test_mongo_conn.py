import asyncio
from pymongo import AsyncMongoClient

async def test_mongo():
    try:
        client = AsyncMongoClient("mongodb://127.0.0.1:27017", serverSelectionTimeoutMS=2000)
        res = await client.admin.command("ping")
        print("MongoDB Ping Result:", res)
        await client.close()
    except Exception as e:
        print("MongoDB Connection Exception:", e)

if __name__ == "__main__":
    asyncio.run(test_mongo())
