# 8) src/server/models/__init__.py  (ersätt om tom)
from .customer import Customer
from .material import Material
from .work_item import WorkItem
from .quote import Quote, QuoteLine

__all_models = [Customer, Material, WorkItem, Quote, QuoteLine]

