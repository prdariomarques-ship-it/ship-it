from models.task import Task
from repositories.base import SQLAlchemyRepository


class TaskRepository(SQLAlchemyRepository[Task]):
    model = Task
