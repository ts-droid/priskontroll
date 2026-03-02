from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class Product(Base):
    __tablename__ = "products"

    id = Column(String, primary_key=True)
    sku = Column(String, unique=True, nullable=False)
    ean = Column(String)
    name = Column(String, nullable=False)
    cost = Column(Float)
    currency = Column(String)
    active = Column(Boolean, nullable=False, default=True)


class InternalCustomer(Base):
    __tablename__ = "internal_customers"

    id = Column(String, primary_key=True)
    external_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    country_code = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now())


class AuthorizedResellerDomain(Base):
    __tablename__ = "authorized_reseller_domains"

    id = Column(String, primary_key=True)
    customer_id = Column(String, ForeignKey("internal_customers.id"))
    customer_external_id = Column(String)
    customer_name = Column(String)
    domain = Column(String, nullable=False, unique=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now())


class ResellerOffer(Base):
    __tablename__ = "reseller_offers"

    id = Column(String, primary_key=True)
    product_id = Column(String, nullable=False)
    competitor_id = Column(String)
    market = Column(String, nullable=False)
    effective_price = Column(Float, nullable=False)
    currency = Column(String, nullable=False)
    offer_url = Column(String)
    captured_at = Column(DateTime, nullable=False)


class InternalSalesLine(Base):
    __tablename__ = "internal_sales_lines"

    id = Column(String, primary_key=True)
    source_system = Column(String, nullable=False)
    external_record_id = Column(String, nullable=False)
    sold_at = Column(DateTime, nullable=False)
    customer_id = Column(String, ForeignKey("internal_customers.id"), nullable=False)
    product_id = Column(String)
    product_sku = Column(String)
    product_ean = Column(String)
    sold_price = Column(Float, nullable=False)
    currency = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
