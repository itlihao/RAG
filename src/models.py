from tortoise.models import Model
from tortoise import fields

class ChatSession(Model):
    id = fields.CharField(pk=True, max_length=36)  # UUID格式的主键
    summary = fields.TextField()
    create_time = fields.DatetimeField(auto_now_add=True)
    updat_time = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "chat_sessions"


class Message(Model):
    id = fields.IntField(pk=True, generated=True)  # 自增主键
    session = fields.ForeignKeyField("models.ChatSession", related_name="messages")
    role = fields.CharField(max_length=20)  # user/assistant/system
    content = fields.TextField()
    create_time = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "messages"