from depot.models import TimeStampedModel, SoftDeletableModel, RevisionMixin
from depot.mixins.timestamp import TimestampMixin


class BaseModel(TimeStampedModel, SoftDeletableModel, RevisionMixin, TimestampMixin):
    class Meta:
        abstract = True
