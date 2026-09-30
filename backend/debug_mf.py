import asyncio
from core.database import AsyncSessionLocal
from core.redis import init_redis, get_redis
from sqlalchemy import text

SCHEME_CODE = "119551"  # change to your actual schemeCode

async def debug():
    # 1) Init Redis
    await init_redis()
    redis = await get_redis()

    # 2) Check holdings row
    async with AsyncSessionLocal() as db:
        result = await db.execute(
    text("SELECT symbol, asset_type, buy_price FROM holdings")
)

        rows = result.fetchall()
        print("\n=== HOLDINGS ===")
        for row in rows:
            print(f"  symbol={row[0]}  assettype={row[1]}  buyprice={row[2]}")

        # Delete holdings with buy_price = 0
        print("\n=== DELETING holdings with buy_price = 0 ===")
        delete_result = await db.execute(text("DELETE FROM holdings WHERE buy_price = 0"))
        await db.commit()
        print(f"  Deleted {delete_result.rowcount} rows")

    # 3) Check Redis key
    print("\n=== REDIS KEYS nav:* ===")
    keys = await redis.keys("nav:*")
    print(f"  Found keys: {keys}")

    val = await redis.get(f"nav:{SCHEME_CODE}")
    print(f"\n  GET nav:{SCHEME_CODE} => {val}")

    if val is None:
        print("  ❌ Redis has NO NAV for this scheme — portfolio will use buy_price")
    else:
        print(f"  ✅ Redis has NAV = {val} — portfolio SHOULD use this")

asyncio.run(debug())
