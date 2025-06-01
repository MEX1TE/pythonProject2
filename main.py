from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from pydantic import BaseModel
from typing import List, Optional
import datetime
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация FastAPI
app = FastAPI()

# Конфигурация базы данных
DATABASE_URL = "postgresql://postgres:dfvgbh1q2w3e@localhost/expressDB"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Модели SQLAlchemy
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    name = Column(String(100), nullable=False)

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    price = Column(Float, nullable=False)
    description = Column(String)
    image_url = Column(String(255))

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    address = Column(String(255), nullable=False)
    total = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)

# Модели Pydantic
class Credentials(BaseModel):
    username: str
    password: str
    phone: str
    email: str
    name: str

    class Config:
        from_attributes = True

class ProductModel(BaseModel):
    id: int
    name: str
    price: float
    description: Optional[str] = None
    image_url: Optional[str] = None

    class Config:
        from_attributes = True

class CartItemModel(BaseModel):
    product: ProductModel
    quantity: int

    class Config:
        from_attributes = True

class OrderModel(BaseModel):
    items: List[CartItemModel]
    address: str
    total: float

    class Config:
        from_attributes = True

# Создание таблиц (без удаления)
Base.metadata.create_all(bind=engine)

# Зависимость для получения сессии БД
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/register")
async def register(credentials: Credentials, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == credentials.username).first():
        logger.error(f"Registration failed: Username {credentials.username} already exists")
        raise HTTPException(status_code=400, detail="Имя пользователя занято")
    if db.query(User).filter(User.email == credentials.email).first():
        logger.error(f"Registration failed: Email {credentials.email} already exists")
        raise HTTPException(status_code=400, detail="Электронная почта уже зарегистрирована")

    new_user = User(
        username=credentials.username,
        password=credentials.password,  # Без хэширования
        phone=credentials.phone,
        email=credentials.email,
        name=credentials.name
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    logger.info(f"User registered: {credentials.username}")
    return {"message": "Регистрация успешна"}

@app.post("/login")
async def login(credentials: Credentials, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == credentials.username).first()
    if not user or user.password != credentials.password:
        logger.error(f"Login failed for {credentials.username}: Invalid credentials")
        raise HTTPException(status_code=401, detail="Неверные данные")
    logger.info(f"User logged in: {credentials.username}")
    return {"access_token": user.username}

@app.get("/products", response_model=List[ProductModel])
async def get_products(db: Session = Depends(get_db)):
    products = db.query(Product).all()
    logger.info(f"Returning {len(products)} products")
    return products

@app.post("/order", response_model=OrderModel)
async def place_order(order: OrderModel, db: Session = Depends(get_db)):
    if not order.items or not order.address or order.total is None:
        logger.error("Order failed: Missing required fields")
        raise HTTPException(status_code=400, detail="Отсутствуют обязательные поля")

    db_order = Order(address=order.address, total=order.total)
    db.add(db_order)
    db.commit()
    db.refresh(db_order)

    for item in order.items:
        db_order_item = OrderItem(
            order_id=db_order.id,
            product_id=item.product.id,
            quantity=item.quantity
        )
        db.add(db_order_item)
    db.commit()
    logger.info(f"Order placed with ID: {db_order.id}")
    return order

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5002)