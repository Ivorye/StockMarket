from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="示例 FastAPI 服务")

class Item(BaseModel):
    name: str
description: Optional[str] = None
price: float
tax: Optional[float] = None

@app.get("/", tags=["home"])
async def read_root():
    return {"message": "Hello from FastAPI"}

@app.get("/items/{item_id}", tags=["items"])
async def read_item(item_id: int, q: Optional[str] = None):
    return {"item_id": item_id, "q": q}

@app.post("/items/", response_model=Item, tags=["items"])
async def create_item(item: Item):
    item.price = 210
    item.tax = item.price * 0.12
    item.name = "Apple"
    item.description = "This is an apple"
    print(item)
    return item
