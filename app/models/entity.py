from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Entity(BaseModel):
    """
    Entity model for assistants.
    """
    __tablename__ = "entities"
    
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    assistant_id = Column(Integer, ForeignKey("assistants.id"), nullable=False)
    
    # Relationship with Assistant model
    assistant = relationship("Assistant", back_populates="entities") 