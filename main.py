from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, Session, declarative_base, relationship
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
import jwt
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация FastAPI
app = FastAPI()

# Конфигурация базы данных
DATABASE_URL = "postgresql://postgres:dfvgbh1q2w3e@localhost/expressDB"  # Замените на ваши данные
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# JWT настройки
SECRET_KEY = "your-secure-secret-key-2025-express"  # Замените на ваш ключ
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 3600  # Пример: 1 час
DEFAULT_USER_ID_FOR_ORDERS = 1  # Используется для заказов без аутентификации


# --- SQLAlchemy модели ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)  # В реальном приложении храните хеш!
    phone = Column(String(20), nullable=True)
    email = Column(String(100), unique=True, index=True, nullable=True)
    name = Column(String(100), nullable=True)


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    price = Column(Float, nullable=False)
    description = Column(String, nullable=True)
    image_url = Column(String(255), nullable=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=False)
    restaurant = relationship("Restaurant", back_populates="products")


class Restaurant(Base):
    __tablename__ = "restaurants"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(String, nullable=True)
    logo_url = Column(String(255), nullable=True)
    address = Column(String(255), nullable=True)
    products = relationship("Product", back_populates="restaurant")


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # True для DEFAULT_USER_ID_FOR_ORDERS
    address = Column(String(255), nullable=False)
    total = Column(Float, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    items = relationship("OrderItem", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    order = relationship("Order", back_populates="items")
    product = relationship("Product")


# --- Pydantic модели ---
class Credentials(BaseModel):
    username: str
    password: str
    phone: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None

    model_config = {
        "from_attributes": True,
    }


class ProductModel(BaseModel):
    id: Optional[int] = None
    name: str
    price: float
    description: Optional[str] = None
    image_url: Optional[str] = None

    model_config = {
        "from_attributes": True,
        "alias_generator": lambda field_name: "imageUrl" if field_name == "image_url" else field_name,
        "populate_by_name": True,
    }


class CartItemCreate(BaseModel):
    productId: int
    quantity: int


class CartItemModel(BaseModel):
    product: ProductModel
    quantity: int

    model_config = {
        "from_attributes": True,
    }


class OrderCreate(BaseModel):
    address: str
    total: float
    items: List[CartItemCreate]


class OrderModel(BaseModel):
    id: Optional[int] = None
    user_id: Optional[int] = None  # Внутреннее имя поля
    address: str
    total: float
    created_at: Optional[datetime] = None  # Внутреннее имя поля
    items: List[CartItemModel]

    model_config = {
        "from_attributes": True,
        "alias_generator": lambda field_name: "userId" if field_name == "user_id"
        else "createdAt" if field_name == "created_at"
        else field_name,
        "populate_by_name": True,
    }


class RestaurantModel(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    logo_url: Optional[str] = None  # Будет доступно как logoUrl в JSON благодаря alias_generator
    address: Optional[str] = None

    model_config = {
        "from_attributes": True,
        "alias_generator": lambda field_name: "logoUrl" if field_name == "logo_url" else field_name,
        "populate_by_name": True,  # Позволяет также использовать алиас при чтении (если нужно)
    }


# --- Зависимости и утилиты ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# --- Эндпоинты FastAPI ---
@app.post("/api/register")
async def register(credentials: Credentials, db: Session = Depends(get_db)):
    try:
        existing_user_by_username = db.query(User).filter(User.username == credentials.username).first()
        if existing_user_by_username:
            logger.warning(f"Registration attempt for existing username: {credentials.username}")
            raise HTTPException(status_code=400, detail="Имя пользователя уже занято")

        if credentials.email:
            existing_user_by_email = db.query(User).filter(User.email == credentials.email).first()
            if existing_user_by_email:
                logger.warning(f"Registration attempt for existing email: {credentials.email}")
                raise HTTPException(status_code=400, detail="Электронная почта уже зарегистрирована")

        new_user = User(
            username=credentials.username,
            password=credentials.password,  # НЕ ХЕШИРУЕТСЯ, ИСПРАВИТЬ В ПРОДАКШЕНЕ!
            phone=credentials.phone or "",
            email=credentials.email or "",
            name=credentials.name or ""
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        logger.info(f"User registered successfully: {new_user.username}")
        return {"message": "Регистрация успешна"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Server error during registration for {credentials.username}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка сервера при регистрации: {str(e)}")


@app.post("/api/token")
async def login(credentials: Credentials, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == credentials.username).first()
    if not user or user.password != credentials.password:  # Сравнение паролей в открытом виде!
        logger.warning(f"Login failed for {credentials.username}: Invalid credentials")  # Изменено с error на warning
        raise HTTPException(status_code=401, detail="Неверные имя пользователя или пароль")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.username}, expires_delta=access_token_expires)
    logger.info(f"User logged in: {credentials.username}")
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/api/products", response_model=List[ProductModel])
async def get_products(db: Session = Depends(get_db)):
    products_orm = db.query(Product).all()
    logger.info(f"Found {len(products_orm)} products from DB.")
    products_to_return = []
    for p_orm in products_orm:
        p_model = ProductModel.model_validate(p_orm)
        logger.info(f"ORM Product ID: {p_orm.id}, Name: {p_orm.name}, DB image_url: '{p_orm.image_url}'")
        logger.info(
            f"Pydantic ProductModel for ID {p_model.id}: Name: {p_model.name}, Model image_url: '{p_model.image_url}'")
        products_to_return.append(p_model)
    logger.info(f"Returning {len(products_to_return)} Pydantic models to client.")
    return products_to_return


@app.get("/api/restaurants", response_model=List[RestaurantModel])
async def get_restaurants(db: Session = Depends(get_db)):
    restaurants_orm = db.query(Restaurant).all()
    logger.info(f"Found {len(restaurants_orm)} restaurants from DB.")
    # Pydantic V2: FastAPI автоматически вызовет model_validate для каждого элемента
    return restaurants_orm


@app.get("/api/restaurants/{restaurant_id}/products", response_model=List[ProductModel])
async def get_products_by_restaurant(restaurant_id: int, db: Session = Depends(get_db)):
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not restaurant:
        logger.warning(f"Restaurant with ID {restaurant_id} not found.")
        raise HTTPException(status_code=404, detail="Restaurant not found")

    products_orm = db.query(Product).filter(Product.restaurant_id == restaurant_id).all()
    logger.info(f"Found {len(products_orm)} products for restaurant ID {restaurant_id}.")
    # Pydantic V2: FastAPI автоматически вызовет model_validate для каждого элемента
    return products_orm


@app.post("/api/orders", response_model=OrderModel)
async def place_order(order: OrderCreate, db: Session = Depends(get_db)):
    try:
        if not order.items:
            logger.warning("Place order attempt with no items.")
            raise HTTPException(status_code=400, detail="Корзина не может быть пустой.")
        if not order.address:
            logger.warning("Place order attempt with no address.")
            raise HTTPException(status_code=400, detail="Адрес доставки не указан.")
        if order.total is None or order.total < 0:
            logger.warning(f"Place order attempt with invalid total: {order.total}")
            raise HTTPException(status_code=400, detail="Некорректная общая сумма заказа.")

        actual_user_id = DEFAULT_USER_ID_FOR_ORDERS

        db_order = Order(
            user_id=actual_user_id,
            address=order.address,
            total=order.total,
        )
        db.add(db_order)
        db.commit()
        db.refresh(db_order)
        logger.info(f"Order created with ID: {db_order.id} for user_id: {actual_user_id}")

        order_items_for_response = []
        for item_req in order.items:
            product_check = db.query(Product).filter(Product.id == item_req.productId).first()
            if not product_check:
                db.rollback()
                logger.error(f"Product with ID {item_req.productId} not found during order placement.")
                raise HTTPException(status_code=404, detail=f"Продукт с ID {item_req.productId} не найден.")

            db_order_item = OrderItem(
                order_id=db_order.id,
                product_id=item_req.productId,
                quantity=item_req.quantity
            )
            db.add(db_order_item)

            product_model_for_item = ProductModel.model_validate(product_check)  # Используем model_validate
            order_items_for_response.append(CartItemModel(product=product_model_for_item, quantity=item_req.quantity))

        db.commit()
        logger.info(f"All items for order ID: {db_order.id} processed and committed.")

        # Используем внутренние имена полей user_id и created_at при создании OrderModel
        return OrderModel(
            id=db_order.id,
            user_id=db_order.user_id,
            address=db_order.address,
            total=db_order.total,
            created_at=db_order.created_at,
            items=order_items_for_response
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Server error during place_order: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера при создании заказа: {str(e)}")


@app.get("/api/orders", response_model=List[OrderModel])
async def get_order_history(db: Session = Depends(get_db)):
    try:
        actual_user_id = DEFAULT_USER_ID_FOR_ORDERS

        orders_db = db.query(Order).filter(Order.user_id == actual_user_id).order_by(Order.created_at.desc()).all()
        logger.info(f"Found {len(orders_db)} orders for user_id: {actual_user_id}")

        response_orders = []
        for order_db_obj in orders_db:
            db_order_items = db.query(OrderItem).filter(OrderItem.order_id == order_db_obj.id).all()
            items_for_response = []
            for db_item_obj in db_order_items:
                if db_item_obj.product:
                    product_model_item = ProductModel.model_validate(db_item_obj.product)  # Используем model_validate
                    items_for_response.append(CartItemModel(product=product_model_item, quantity=db_item_obj.quantity))
                else:
                    logger.warning(
                        f"Order item ID {db_item_obj.id} for order ID {order_db_obj.id} references a non-existent product ID {db_item_obj.product_id}")

            # Используем внутренние имена полей user_id и created_at при создании OrderModel
            response_orders.append(OrderModel(
                id=order_db_obj.id,
                user_id=order_db_obj.user_id,
                address=order_db_obj.address,
                total=order_db_obj.total,
                created_at=order_db_obj.created_at,
                items=items_for_response
            ))
        logger.info(f"Returning {len(response_orders)} orders in history.")
        return response_orders
    except Exception as e:
        logger.error(f"Server error during get_order_history: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500,
                            detail=f"Внутренняя ошибка сервера при получении истории заказов: {str(e)}")


# --- Запуск сервера ---
if __name__ == "__main__":
    import uvicorn

    #Base.metadata.create_all(bind=engine)  # Раскомментировано для создания таблиц
    logger.info("Attempting to create database tables if they don't exist...")  # Можно оставить для лога
    # try:
    #     Base.metadata.create_all(bind=engine)
    #     logger.info("Database tables checked/created successfully.")
    # except Exception as e:
    #     logger.error(f"Error creating database tables: {e}", exc_info=True)

    logger.info("Starting Uvicorn server on http://0.0.0.0:5002")
    uvicorn.run(app, host="0.0.0.0", port=5002)